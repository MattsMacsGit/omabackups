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
  readonly property var targets: step === "migrating" ? [carryOn]
    : [restartButton, restoreButton, stopButton, again].filter(function(t) { return t.visible })
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
    visible: page.step === "finish" && !page.m.files_restored
    width: parent.width
    color: page.service ? page.service.colour("blue") : Commons.Color.foreground
    text: page.restoringNow ? "Bringing back your files · " + (page.r.percent || 0) + "%" : "Restore my files to finish"
  }
  Prose {
    visible: page.step === "finish" && !page.m.files_restored && !page.restoringNow
    width: parent.width
    dim: true
    text: (page.r && page.r.error ? page.r.error.what + " " : "")
          + "Your files are still in the restore point from " + page.whenOf(page.m.point)
          + ". They come back while you work; a file that's newer here is never overwritten."
  }
  Prose {
    visible: page.step === "finish" && !page.m.files_restored && !page.restoringNow
             && !!(page.m.files_here && page.m.files_here.length)
    width: parent.width
    color: page.service ? page.service.colour("yellow") : Commons.Color.foreground
    text: "Already here: " + (page.m.files_here || []).join(", ")
          + ". Old files are added beside what's in them; move a working copy aside first."
  }
  ActionButton {
    id: restoreButton
    visible: page.step === "finish" && !page.m.files_restored && !page.restoringNow
    width: parent.width
    text: "Restore my files"
    hasCursorHere: page.cursorOn(this)
    onClicked: page.service.restoreFiles(page.m.point)
  }
  ActionButton {
    id: stopButton
    visible: page.step === "finish" && page.restoringNow
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

  PanelSeparator { visible: page.step === "finish" }
  NavRow {
    id: again
    visible: page.step === "finish"
    title: "Run Migrate again"
    explainer: "Brings back the migration chooser, so you can pick any preferences you left behind: "
               + "you can still recover them here."
    hasCursorHere: page.cursorOn(this)
    onActivated: page.service.migrateContinue()
  }
}
