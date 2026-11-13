import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "../parts"
import "../Model.js" as Model

// Migrate on the panel (BUILD 6.1 F): carrying on an unfinished Migrate, and
// finishing one: Restart to finish (only if a System tweak needs it), Restore
// my files to finish, and Run Migrate again (D38).
Column {
  id: page
  property var service: null
  property var panel: null
  property string step: "migrating"      // migrating | finish
  spacing: Style.space(10)

  readonly property var m: service && service.status.migrate ? service.status.migrate : ({})
  readonly property var r: service ? service.restoring : null
  readonly property bool restoringNow: !!(r && r.running)
  // D52: after a Quick Rescue, folders come back as you choose, as often as you
  // like, until Back up now ends it.
  readonly property bool rescuedFlow: !!(m.rescued && m.files && m.files.length)
  readonly property bool showRestore: step === "finish" && (rescuedFlow || !m.files_restored)
  property var picks: ({})
  function brought(name) { return (m.brought || []).indexOf(name) >= 0 }
  function ticked(name) { return picks[name] !== undefined ? picks[name] : !brought(name) }
  function tickedList() { return (m.files || []).filter(function(f) { return page.ticked(f) }) }
  onRestoringNowChanged: if (!restoringNow) picks = ({})      // a run ended: ticks follow what's back
  readonly property var targets: step === "migrating" ? [carryOn]
    : [restartButton].concat(folderRows(), [restoreButton, stopButton, backUp, again])
        .filter(function(t) { return t && t.visible })
  function folderRows() {
    var out = []
    for (var i = 0; i < folderRepeater.count; i++) out.push(folderRepeater.itemAt(i))
    return out
  }
  function cursorOn(item) { return panel && panel.cursorTarget === item }
  function whenOf(name) {
    var p = /^(\d{3})-(\d{4})-(\d{2})-(\d{2})-(\d{2})(\d{2})$/.exec(name || "")
    return p ? Model.capital(Model.when(new Date(+p[2], +p[3] - 1, +p[4], +p[5], +p[6]).getTime() / 1000)) : name
  }

  // --- Migrate started, not finished -----------------------------------------------------
  Prose { visible: page.step === "migrating"; width: parent.width; text: "Migrate isn't finished on this computer yet." }
  NavRow {
    id: carryOn
    visible: page.step === "migrating"
    title: "Carry on with Migrate"
    explainer: "Opens it in a terminal window: pick the restore point, then choose what comes over."
    hasCursorHere: page.cursorOn(this)
    onActivated: page.service.migrateContinue()
  }

  // --- Finishing ------------------------------------------------------------------------
  Prose {
    visible: page.step === "finish" && !!page.m.restart_needed
    width: parent.width
    color: page.service ? page.service.colour("blue") : Commons.Color.foreground
    text: "Restart to finish"
  }
  Prose {
    visible: page.step === "finish" && !!page.m.restart_needed
    width: parent.width
    dim: true
    text: "Your logins, services and desktop come back as they were after a restart."
  }
  ActionButton {
    id: restartButton
    visible: page.step === "finish" && !!page.m.restart_needed
    width: parent.width
    text: "Restart now"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.restartNow()
  }

  Prose {
    visible: page.showRestore
    width: parent.width
    color: page.service ? page.service.colour("blue") : Commons.Color.foreground
    text: page.restoringNow ? "Bringing back your files · " + (page.r.percent || 0) + "%"
          : page.rescuedFlow ? "Bring back your files" : "Restore my files to finish"
  }
  Prose {
    visible: page.showRestore && !page.restoringNow
    width: parent.width
    dim: true
    text: (page.r && page.r.error ? page.r.error.what + " " : "")
          + (page.rescuedFlow
             ? "Your folders are in the restore point from " + page.whenOf(page.m.point)
               + ". Tick the ones to bring back. You can bring back more, or the same ones again, "
               + "as often as you like; a file that's newer here is never overwritten."
             : "Your files are still in the restore point from " + page.whenOf(page.m.point)
               + ". They come back while you work; a file that's newer here is never overwritten.")
  }
  Repeater {
    id: folderRepeater
    model: page.rescuedFlow && page.step === "finish" ? page.m.files : []
    SwitchRow {
      required property var modelData
      width: parent.width
      visible: !page.restoringNow
      title: modelData
      explainer: page.brought(modelData) ? "Back on this computer."
                 : (page.m.files_here || []).indexOf(modelData) >= 0
                   ? "Something's already here: the old files are added beside it."
                   : "Still in your backup."
      checked: page.ticked(modelData)
      hasCursorHere: page.cursorOn(this)
      onToggled: {
        var p = Object.assign({}, page.picks)
        p[modelData] = !page.ticked(modelData)
        page.picks = p
      }
    }
  }
  Prose {
    visible: page.showRestore && !page.restoringNow && !page.rescuedFlow
             && !!(page.m.files_here && page.m.files_here.length)
    width: parent.width
    color: page.service ? page.service.colour("yellow") : Commons.Color.foreground
    text: "Already here: " + (page.m.files_here || []).join(", ")
          + ". Old files are added beside what's in them; move a working copy aside first."
  }
  ActionButton {
    id: restoreButton
    visible: page.showRestore && !page.restoringNow
    width: parent.width
    readonly property int count: page.tickedList().length
    text: page.rescuedFlow ? "Bring back the ticked folders (" + count + ")" : "Restore my files"
    enabled: !page.rescuedFlow || count > 0
    hasCursorHere: page.cursorOn(this)
    onClicked: page.rescuedFlow ? page.service.restoreFiles(page.m.point, page.tickedList())
                                : page.service.restoreFiles(page.m.point)
  }
  ActionButton {
    id: stopButton
    visible: page.showRestore && page.restoringNow
    width: parent.width
    text: "Stop (carry on later)"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.restoreStop()
  }

  Prose {
    visible: page.step === "finish" && !!(page.r && page.r.note)
    width: parent.width
    color: page.service ? page.service.colour("yellow") : Commons.Color.foreground
    text: page.r && page.r.note ? page.r.note : ""
  }

  // D52: a backup ends the restore; the panel then goes to its everyday page.
  PanelSeparator { visible: backUp.visible || backingUp.visible }
  Prose {
    visible: backUp.visible
    width: parent.width
    dim: true
    text: "When everything you want is back, back up: that finishes the restore, and "
          + "automatic backups carry on from there."
  }
  ActionButton {
    id: backUp
    visible: page.step === "finish" && page.rescuedFlow && !page.restoringNow
             && !(page.service && page.service.running)
    width: parent.width
    text: "Back up now"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.backupNow()
  }
  BackupProgress {
    id: backingUp
    visible: page.step === "finish" && page.rescuedFlow && !!(page.service && page.service.running)
    width: parent.width
    running: page.service ? page.service.running : null
    barColour: page.service ? page.service.colour("blue") : Commons.Color.accent
  }

  PanelSeparator { visible: page.step === "finish" && !page.m.rescued }
  NavRow {
    id: again
    visible: page.step === "finish" && !page.m.rescued      // a rescued computer is the same one
    title: "Run Migrate again"
    explainer: "Brings back the migration chooser, so you can pick any preferences you left behind: "
               + "you can still recover them here."
    hasCursorHere: page.cursorOn(this)
    onActivated: page.service.migrateContinue()
  }
}
