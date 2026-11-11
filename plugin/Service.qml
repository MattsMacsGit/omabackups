import QtQuick
import Quickshell
import Quickshell.Io

// Talks to the omabackups command (D19: the panel only shows things and presses
// its buttons). Status comes from `omabackups --json status`: often while a
// backup runs, every few seconds while the panel is open, else every 30 s, and
// at once when the backup's own files change. Colours come from the live theme.
Item {
  id: root

  property bool panelOpen: false
  property bool installed: true
  property bool loaded: false
  property var status: ({})
  property string notice: ""
  property string noticeDetails: ""

  readonly property string flow: status.flow || ""
  // Back up now and Stop show at once (a button reacts the moment it's pressed:
  // the user sees it was pushed); the status checks catch up after.
  property double startAsked: 0
  property bool stopAsked: false
  readonly property var running: status.running
      ? (stopAsked ? Object.assign({}, status.running, { stopping: true }) : status.running)
      : (startAsked ? { step: "starting" } : null)
  onStatusChanged: {
    if (status.running) startAsked = 0
    else stopAsked = false
    // A backup that didn't start (the away limit, a problem) goes back after a while.
    if (startAsked && Date.now() - startAsked > 15000) startAsked = 0
  }
  readonly property var header: status.header || null
  // D32: a switch shows its new state at once. `expected` holds what the
  // panel asked for until status confirms it (or the command fails: then it
  // goes, and the switch flips back).
  property var expected: ({})
  readonly property var points: (status.points || []).map(function(p) {
    var want = root.expected["keep:" + p.name]
    return want === undefined ? p : Object.assign({}, p, { kept: want })
  })
  readonly property var lines: status.lines || []
  readonly property var settings: {
    var out = Object.assign({}, status.settings || {})
    for (var key in root.expected)
      if (key.indexOf("setting:") === 0) out[key.slice(8)] = root.expected[key]
    return out
  }
  readonly property bool firstBackupDone: status.first_backup_done === true
  // D37: the restore point open in the file manager, and Restore my files.
  readonly property var browsing: status.browsing && status.browsing.ready ? status.browsing : null
  readonly property string opening: expected["browse"] !== undefined
                                    && !(browsing && browsing.point === expected["browse"]) ? expected["browse"] : ""
  readonly property var restoring: status.restoring || null

  // The live theme's status colours (BUILD 7.0); fallbacks until it's read.
  property var theme: ({ green: "#9ece6a", blue: "#7aa2f7", yellow: "#e0af68", red: "#f7768e" })

  function colour(name) { return theme[name] || theme.blue }

  // --- reading ---------------------------------------------------------------

  function lastResult(text) {
    var rows = String(text || "").trim().split("\n")
    for (var i = rows.length - 1; i >= 0; i--) {
      try {
        var event = JSON.parse(rows[i])
        if (event.event === "result" || event.event === "error") return event
      } catch (e) {}
    }
    return null
  }

  function refresh() {
    if (statusProc.running) return
    statusProc.startedAfter = root.actionsDone
    statusProc.running = true
  }

  Process {
    id: statusProc
    property int startedAfter: 0
    command: ["sh", "-c", "command -v omabackups >/dev/null || exit 127; exec omabackups --json status"]
    stdout: StdioCollector { id: statusOut; waitForEnd: true }
    onExited: function(code) {
      if (code === 127) { root.installed = false; root.loaded = true; return }
      root.installed = true
      var result = root.lastResult(statusOut.text)
      if (result && result.event === "result") {
        root.status = result
        root.loaded = true
        // Status read after every asked-for change: it shows them now.
        if (startedAfter === root.actionsDone && !actionProc.running && root.queue.length === 0)
          root.expected = ({})
      }
    }
  }

  Timer {
    interval: root.running ? 1500 : (root.panelOpen ? 5000 : 30000)
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  FileView { path: "/run/omabackups/progress.json"; watchChanges: true; onFileChanged: root.refresh() }
  FileView { path: "/var/lib/omabackups/backup.json"; watchChanges: true; onFileChanged: root.refresh() }
  FileView { path: "/run/omabackups/browse.json"; watchChanges: true; printErrors: false; onFileChanged: root.refresh() }
  FileView { path: "/run/omabackups/restore.json"; watchChanges: true; printErrors: false; onFileChanged: root.refresh() }

  FileView {
    id: themeFile
    path: Quickshell.env("HOME") + "/.local/state/omarchy/current/theme/colors.toml"
    watchChanges: true
    onFileChanged: reload()
    onLoaded: root.readTheme(text())
  }

  function readTheme(text) {
    var found = {}
    String(text || "").split("\n").forEach(function(row) {
      var m = row.match(/^\s*(green|blue|yellow|red)\s*=\s*"(#[0-9a-fA-F]{6})"/)
      if (m) found[m[1]] = m[2]
    })
    if (Object.keys(found).length) root.theme = Object.assign({}, root.theme, found)
  }

  // --- doing ----------------------------------------------------------------------

  // A quick command; its error (what happened, what to do, details) becomes the notice.
  // Clicks wait their turn: none is dropped while an earlier one runs (D32).
  property var queue: []
  property int actionsDone: 0

  Process {
    id: actionProc
    property string expects: ""
    stdout: StdioCollector { id: actionOut; waitForEnd: true }
    onExited: function(code) {
      var result = root.lastResult(actionOut.text)
      if (code !== 0) {
        root.notice = result && result.event === "error" ? (result.what + " " + (result.todo || "")).trim()
                                                         : "That didn't work: the omabackups command stopped."
        root.noticeDetails = result && result.details ? result.details : ""
        if (expects !== "") {         // flip it back
          var undo = Object.assign({}, root.expected)
          delete undo[expects]
          root.expected = undo
        }
      }
      root.actionsDone++
      root.next()
    }
  }

  function run(args, expectKey, expectValue) {
    if (expectKey) {
      var want = Object.assign({}, expected)
      want[expectKey] = expectValue
      expected = want
    }
    notice = ""
    noticeDetails = ""
    queue = queue.concat([{ args: args, expects: expectKey || "" }])
    if (!actionProc.running) next()
  }

  function next() {
    if (queue.length === 0) { refresh(); return }
    var job = queue[0]
    queue = queue.slice(1)
    actionProc.expects = job.expects
    actionProc.command = ["omabackups", "--json"].concat(job.args)
    actionProc.running = true
  }

  // Long jobs run on their own (the panel follows them through status).
  function start(args) { Quickshell.execDetached(["omabackups"].concat(args)); Qt.callLater(refresh) }

  // A terminal window for the picker and for typing passwords (Omarchy's launcher
  // joins its arguments, so it gets one command string: 1.x lesson).
  function terminal(command) {
    Quickshell.execDetached(["omarchy-launch-floating-terminal-with-presentation", command])
  }

  function backupNow() {
    // D29: the very first backup opens the picker first; saving starts it.
    if (!firstBackupDone) terminal("omabackups pick --then-backup")
    else { startAsked = Date.now(); start(["backup"]) }
  }
  function stop() { stopAsked = true; run(["stop"]) }
  function awayAnswer(now) { if (now) start(["away", "answer", "now"]); else run(["away", "answer", "wait"]) }
  function setSetting(name, value) { run(["settings", "set", name, String(value)], "setting:" + name, value) }
  function keep(point, on) { run([on ? "keep" : "release", point], "keep:" + point, on) }
  function rescueLater() { run(["rescue-usb", "later"]) }
  // Make / Refresh Rescue USB (9c): a terminal window, like setup (it downloads,
  // asks which stick, and the computer's password for writing it).
  function rescueMake() { terminal("omabackups rescue-usb make") }
  function rescueRefresh() { terminal("omabackups rescue-usb refresh") }
  // Opens it in the default file manager (the command does that, D37).
  function browse(point) { run(["browse", point], "browse", point) }
  function browseDone() { run(["browse", "done"]) }
  function restoreFiles(point) { run(["restore-files", point]) }
  function restoreStop() { run(["restore-files", "stop"]) }
  function startOver() { run(["start-over"]) }
  function pick() { terminal("omabackups pick") }
  function changePassword() { terminal("omabackups password change") }
  function setupServer(address, login) {
    terminal("omabackups setup server " + shellWord(address) + " --login " + shellWord(login))
  }
  function setupDisk() { terminal("omabackups setup disk") }
  // Migrate (6.1 F) and Run Migrate again (D38), in a terminal window.
  function migrate(address, login) {
    terminal("omabackups migrate " + shellWord(address) + " --login " + shellWord(login))
  }
  function migrateContinue() { terminal("omabackups migrate") }
  function restartNow() { Quickshell.execDetached(["systemctl", "reboot"]) }
  function installPackage() { terminal("omarchy-pkg-aur-add omabackups") }

  // One word for the shell, whatever was typed (never interpolated raw).
  function shellWord(text) { return "'" + String(text).replace(/'/g, "'\\''") + "'" }
}
