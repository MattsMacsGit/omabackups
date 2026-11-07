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
  property var changes: null
  property string notice: ""
  property string noticeDetails: ""

  readonly property string flow: status.flow || ""
  readonly property var running: status.running || null
  readonly property var header: status.header || null
  readonly property var points: status.points || []
  readonly property var lines: status.lines || []
  readonly property var settings: status.settings || ({})
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

  function refresh() { if (!statusProc.running) statusProc.running = true }

  Process {
    id: statusProc
    command: ["sh", "-c", "command -v omabackups >/dev/null || exit 127; exec omabackups --json status"]
    stdout: StdioCollector { id: statusOut; waitForEnd: true }
    onExited: function(code) {
      if (code === 127) { root.installed = false; root.loaded = true; return }
      root.installed = true
      var result = root.lastResult(statusOut.text)
      if (result && result.event === "result") { root.status = result; root.loaded = true }
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
  Process {
    id: actionProc
    stdout: StdioCollector { id: actionOut; waitForEnd: true }
    onExited: function(code) {
      var result = root.lastResult(actionOut.text)
      if (code !== 0 && result && result.event === "error") {
        root.notice = (result.what + " " + (result.todo || "")).trim()
        root.noticeDetails = result.details || ""
      }
      if (result && result.event === "result" && result.items) root.changes = result
      root.refresh()
    }
  }

  function run(args) {
    if (actionProc.running) return
    notice = ""
    noticeDetails = ""
    actionProc.command = ["omabackups", "--json"].concat(args)
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
  function setSetting(name, value) { run(["settings", "set", name, String(value)]) }
  function keep(point, on) { run([on ? "keep" : "release", point]) }
  function rescueLater() { run(["rescue-usb", "later"]) }
  function loadChanges() { run(["changes"]) }
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
