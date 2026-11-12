import QtQuick
import Quickshell
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "../parts"
import "../Model.js" as Model

// Before everyday (BUILD 6.1 A-C, agreed 7 Nov): the package missing, the
// first start, and Set up backups one step per screen.
Column {
  id: page
  property var service: null
  property var panel: null
  property string step: "first"       // missing | first | where | server | disk | firstBackup
  spacing: Style.space(12)

  readonly property var targets: {
    if (step === "missing") return [install]
    if (step === "first") return [setUp, migrate]
    if (step === "where") return [toServer, toDisk]
    if (step === "server") return [address, login, goServer]
    if (step === "disk") return [goDisk]
    if (step === "firstBackup") return firstLines().concat(service && service.running ? [firstStop, makeStick, later]
                                       : [firstBackup, migrateAgain]).filter(function(t) { return t.visible })
    return []
  }
  function cursorOn(item) { return panel && panel.cursorTarget === item }
  function firstLines() {
    var out = []
    for (var i = 0; i < firstLineRepeater.count; i++) {
      var line = firstLineRepeater.itemAt(i)
      var own = line ? Array.prototype.filter.call(line.buttonItems, function(b) { return b.visible }) : []
      if (own.length) own.forEach(function(b) { out.push(b) })
      else if (line) out.push(line)
    }
    return out
  }
  // The same Where and server screens serve Migrate (6.1 F step 1).
  readonly property bool migrating: !!(panel && panel.migrateMode)

  Prose {
    visible: ["where", "server", "disk", "firstBackup"].indexOf(page.step) >= 0
    width: parent.width
    dim: true
    text: page.migrating && page.step !== "firstBackup"
          ? "Migrate · step 1 of 4: connect to your old computer's backup"
          : "Set up backups · step " + ({ where: 1, server: 2, disk: 2, firstBackup: 3 })[page.step] + " of 3"
  }

  // --- A. The package isn't installed -------------------------------------------
  Prose { visible: page.step === "missing"; width: parent.width; text: "The OmaBackups plugin needs the omabackups package." }
  NavRow {
    id: install
    visible: page.step === "missing"
    title: "Install it"
    explainer: "From the AUR, in a terminal window. It asks for your password once."
    hasCursorHere: page.cursorOn(this)
    onActivated: page.service.installPackage()
  }

  // --- B. First start: two choices only ---------------------------------------------
  NavRow {
    id: setUp
    visible: page.step === "first"
    title: "Set up backups"
    explainer: "Back up this computer to a backup server or a disk plugged in here."
    hasCursorHere: page.cursorOn(this)
    onActivated: { page.panel.migrateMode = false; page.panel.go("where") }
  }
  NavRow {
    id: migrate
    visible: page.step === "first"
    title: "Migrate from another system"
    explainer: "Choose the preferences and settings you'd like to keep from a previous install, "
               + "and bring them over."
    hasCursorHere: page.cursorOn(this)
    onActivated: { page.panel.migrateMode = true; page.panel.go("where") }
  }

  // --- C1. Where? ----------------------------------------------------------------------
  Prose {
    visible: page.step === "where"
    width: parent.width
    text: page.migrating ? "Where is your old computer's backup?" : "Where should your backups go?"
  }
  NavRow {
    id: toServer
    visible: page.step === "where"
    title: "A backup server on the network"
    explainer: page.migrating ? "The backup server your old computer backed up to."
                              : "Any always-on Linux computer (a Pi, an old laptop). Backs up wherever you are."
    hasCursorHere: page.cursorOn(this)
    onActivated: page.panel.go("server")
  }
  NavRow {
    id: toDisk
    visible: page.step === "where"
    title: "A backup disk plugged in here"
    explainer: page.migrating ? "Migrating from a backup disk comes with a later version."
                              : "A USB disk. It's erased and used only for your backups."
    enabledRow: !page.migrating
    hasCursorHere: page.cursorOn(this)
    onActivated: page.panel.go("disk")
  }

  // --- C2. Details: a server ----------------------------------------------------------
  Prose { visible: page.step === "server"; width: parent.width; text: "The server's address" }
  TextField {
    id: address
    visible: page.step === "server"
    width: parent.width
    placeholderText: "for example 192.168.1.20"
    hasCursor: page.cursorOn(this)
    function activate() { forceActiveFocus() }
  }
  Prose { visible: page.step === "server"; width: parent.width; text: "Your user name on the server" }
  TextField {
    id: login
    visible: page.step === "server"
    width: parent.width
    text: Quickshell.env("USER") || ""
    hasCursor: page.cursorOn(this)
    function activate() { forceActiveFocus() }
  }
  ActionButton {
    id: goServer
    width: parent.width
    visible: page.step === "server"
    enabled: address.text.trim() !== "" && login.text.trim() !== ""
    text: "Continue in a terminal window"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.migrating ? page.service.migrate(address.text.trim(), login.text.trim())
                              : page.service.setupServer(address.text.trim(), login.text.trim())
  }
  Prose {
    visible: page.step === "server"
    width: parent.width
    dim: true
    text: page.migrating
          ? "A window opens for the passwords: this computer's, your password on the server twice (to log "
            + "in, then for sudo), then your backup's own. Then you pick the restore point and choose "
            + "what comes over."
          : "The rest needs passwords: this computer's, your login on the server, and the server's sudo "
            + "password. A window opens for them, then asks where on the server your backup goes and "
            + "its own password. This panel moves on by itself when it's done."
  }

  // --- C2. Details: a disk --------------------------------------------------------------
  Prose { visible: page.step === "disk"; width: parent.width; text: "Plug in the disk you want to use, then continue." }
  ActionButton {
    id: goDisk
    width: parent.width
    visible: page.step === "disk"
    text: "Continue in a terminal window"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.setupDisk()
  }
  Prose {
    visible: page.step === "disk"
    width: parent.width
    dim: true
    text: "It lists every disk with what's on it: the one you pick is erased. Then it asks for this "
          + "computer's password and your backup's own password. This panel moves on by itself."
  }

  // --- C3. The first backup, with the Rescue USB beside it (D29, D11) ---------------------
  // D50: why a backup didn't finish is always on screen, here too (only the
  // everyday page showed the lines; the bar icon just went red).
  Repeater {
    id: firstLineRepeater
    model: page.step === "firstBackup" && page.service ? page.service.lines : []
    StatusLine {
      required property var modelData
      width: parent.width
      item: modelData
      service: page.service
      hasCursorHere: page.cursorOn(this)
      onActivated: {
        if (modelData.action === "pick") page.service.pickAgain()
        else if (modelData.kind === "failed" || modelData.kind === "unreachable") page.service.backupOrResume()
      }
      buttons: [
        ActionButton {
          visible: modelData.kind === "waiting-network"
          text: "Back up now"
          hasCursorHere: page.cursorOn(this)
          onClicked: page.service.awayAnswer(true)
        },
        ActionButton {
          visible: modelData.kind === "waiting-network"
          text: "Wait until I'm on a known network"
          hasCursorHere: page.cursorOn(this)
          onClicked: page.service.awayAnswer(false)
        }
      ]
    }
  }
  Prose {
    visible: page.step === "firstBackup" && !(page.service && page.service.running)
    width: parent.width
    text: page.service && page.service.status.migrate
          ? "Your first backup makes this computer the backup's owner. Only what's changed since the old "
            + "computer's restore point is stored, and that restore point is kept as your Return point. "
            + "First you choose what gets backed up."
          : "Your first backup copies everything, so it takes a while. First you choose what gets "
            + "backed up: your own files are ticked, and the trash and caches are skipped."
  }
  NavRow {
    // D40: until the takeover (this first backup), anything left behind can still come over.
    id: migrateAgain
    visible: page.step === "firstBackup" && !(page.service && page.service.running)
             && !!(page.service && page.service.status.migrate)
    title: "Run Migrate again"
    explainer: "Brings back the migration chooser, so you can pick any preferences you left behind "
               + "before this computer takes the backup over."
    hasCursorHere: page.cursorOn(this)
    onActivated: page.service.migrateContinue()
  }
  ActionButton {
    id: firstBackup
    width: parent.width
    visible: page.step === "firstBackup" && !(page.service && page.service.running)
    // D49: stopped or cut off, the first backup carries on from its list (no picker again).
    readonly property bool resumes: !!(page.service && page.service.status.unfinished)
    text: resumes ? "Resume backup" : "Back up now"
    hasCursorHere: page.cursorOn(this)
    onClicked: resumes ? page.service.resume() : page.service.backupNow()
  }
  BackupProgress {
    visible: page.step === "firstBackup" && !!(page.service && page.service.running)
    width: parent.width
    running: page.service ? page.service.running : null
    barColour: page.service ? page.service.colour("blue") : Commons.Color.accent
  }
  ActionButton {
    id: firstStop
    visible: page.step === "firstBackup" && !!(page.service && page.service.running)
    readonly property bool stopping: !!(page.service && page.service.running && page.service.running.stopping)
    text: stopping ? "Stopping…" : "Stop"
    enabled: !stopping
    hasCursorHere: page.cursorOn(this)
    onClicked: if (!stopping) page.service.stop()
  }
  Prose {
    visible: firstStop.visible
    width: parent.width
    dim: true
    text: "Stopping is safe: Resume backup carries on from where it got to."
  }
  PanelSeparator { visible: page.step === "firstBackup" && !!(page.service && page.service.running) }
  Prose {
    visible: page.step === "firstBackup" && !!(page.service && page.service.running) && !page.service.status.rescue_later
             && !page.service.status.rescue_usb
    width: parent.width
    text: "While you wait: make a Rescue USB"
  }
  Prose {
    visible: page.step === "firstBackup" && !!(page.service && page.service.running) && !page.service.status.rescue_later
             && !page.service.status.rescue_usb
    width: parent.width
    dim: true
    text: "A USB stick that brings this computer back if it won't start. Both run at once: the "
          + "backup takes a while anyway."
  }
  ActionButton {
    id: makeStick
    visible: later.visible
    text: "Make Rescue USB"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.rescueMake()
  }
  ActionButton {
    id: later
    visible: page.step === "firstBackup" && !!(page.service && page.service.running) && !page.service.status.rescue_later
             && !page.service.status.rescue_usb
    text: "Later"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.rescueLater()
  }
}
