import QtQuick
import Quickshell
import qs.Commons
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
    if (step === "firstBackup") return service && service.running ? [later] : [firstBackup]
    return []
  }
  function cursorOn(item) { return panel && panel.cursorTarget === item }

  Prose {
    visible: ["where", "server", "disk", "firstBackup"].indexOf(page.step) >= 0
    width: parent.width
    dim: true
    text: "Set up backups · step " + ({ where: 1, server: 2, disk: 2, firstBackup: 3 })[page.step] + " of 3"
  }

  // --- A. The package isn't installed -------------------------------------------
  Prose { visible: page.step === "missing"; width: parent.width; text: "The OmaBackups plugin needs the omabackups package." }
  ActionButton {
    id: install
    visible: page.step === "missing"
    text: "Install"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.installPackage()
  }
  Prose { visible: page.step === "missing"; width: parent.width; dim: true; text: "Installs it from the AUR in a terminal window. It asks for your password once." }

  // --- B. First start: two choices only ---------------------------------------------
  ActionButton {
    id: setUp
    visible: page.step === "first"
    text: "Set up backups"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.panel.go("where")
  }
  Prose { visible: page.step === "first"; width: parent.width; dim: true; text: "Back up this computer to a backup server or a disk plugged in here." }
  ActionButton {
    id: migrate
    visible: page.step === "first"
    text: "Migrate from another system"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.notice = "Migrate comes with a later version of OmaBackups."
  }
  Prose { visible: page.step === "first"; width: parent.width; dim: true; text: "Bring your apps and settings over from another computer's backup." }

  // --- C1. Where? ----------------------------------------------------------------------
  Prose { visible: page.step === "where"; width: parent.width; text: "Where should your backups go?" }
  ActionButton {
    id: toServer
    visible: page.step === "where"
    text: "A backup server on the network"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.panel.go("server")
  }
  Prose { visible: page.step === "where"; width: parent.width; dim: true; text: "Any always-on Linux computer (a Pi, an old laptop). Backs up wherever you are." }
  ActionButton {
    id: toDisk
    visible: page.step === "where"
    text: "A backup disk plugged in here"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.panel.go("disk")
  }
  Prose { visible: page.step === "where"; width: parent.width; dim: true; text: "A USB disk. It's erased and used only for your backups." }

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
    visible: page.step === "server"
    enabled: address.text.trim() !== "" && login.text.trim() !== ""
    text: "Continue in a terminal window"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.setupServer(address.text.trim(), login.text.trim())
  }
  Prose {
    visible: page.step === "server"
    width: parent.width
    dim: true
    text: "The rest needs passwords: this computer's, your login on the server, and the server's sudo "
          + "password. A window opens for them, then asks where on the server your backup goes and "
          + "its own password. This panel moves on by itself when it's done."
  }

  // --- C2. Details: a disk --------------------------------------------------------------
  Prose { visible: page.step === "disk"; width: parent.width; text: "Plug in the disk you want to use, then continue." }
  ActionButton {
    id: goDisk
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
  Prose {
    visible: page.step === "firstBackup" && !(page.service && page.service.running)
    width: parent.width
    text: "Your first backup copies everything, so it takes a while. First you choose what gets "
          + "backed up: your own files are ticked, and the trash and caches are skipped."
  }
  ActionButton {
    id: firstBackup
    visible: page.step === "firstBackup" && !(page.service && page.service.running)
    text: "Back up now"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.backupNow()
  }
  Prose {
    visible: page.step === "firstBackup" && !!(page.service && page.service.running)
    width: parent.width
    text: Model.doing(page.service ? page.service.running : null)
  }
  PanelSeparator { visible: page.step === "firstBackup" && !!(page.service && page.service.running) }
  Prose {
    visible: page.step === "firstBackup" && !!(page.service && page.service.running) && !page.service.status.rescue_later
    width: parent.width
    text: "While you wait: make a Rescue USB"
  }
  Prose {
    visible: page.step === "firstBackup" && !!(page.service && page.service.running) && !page.service.status.rescue_later
    width: parent.width
    dim: true
    text: "A USB stick that brings this computer back if it won't start. Making one comes with a later "
          + "version of OmaBackups; until then the panel reminds you."
  }
  ActionButton {
    id: later
    visible: page.step === "firstBackup" && !!(page.service && page.service.running) && !page.service.status.rescue_later
    text: "Later"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.rescueLater()
  }
}
