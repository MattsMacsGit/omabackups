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
  readonly property var running: status.running || null
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
    else start(["backup"])
  }
  function stop() { run(["stop"]) }
  function awayAnswer(now) { if (now) start(["away", "answer", "now"]); else run(["away", "answer", "wait"]) }
  function setSetting(name, value) { run(["settings", "set", name, String(value)], "setting:" + name, value) }
  function keep(point, on) { run([on ? "keep" : "release", point], "keep:" + point, on) }
  function rescueLater() { run(["rescue-usb", "later"]) }
  function startOver() { run(["start-over"]) }
  function pick() { terminal("omabackups pick") }
  function changePassword() { terminal("omabackups password change") }
  function setupServer(address, login) {
    terminal("omabackups setup server " + shellWord(address) + " --login " + shellWord(login))
  }
  function setupDisk() { terminal("omabackups setup disk") }
  function installPackage() { terminal("omarchy-pkg-aur-add omabackups") }

  // One word for the shell, whatever was typed (never interpolated raw).
  function shellWord(text) { return "'" + String(text).replace(/'/g, "'\\''") + "'" }
}
