import QtQuick
import qs.Commons
import qs.Ui
import "../parts"
import "../Model.js" as Model

// Settings' detail pages (BUILD 6.1 E, 7.1, D35): Restore points (smart
// thinning and the kept ones), and Your backup.
Column {
  id: page
  property var service: null
  property var panel: null
  property string step: "kept"          // kept (Restore points) | yourBackup
  property bool confirming: false
  spacing: Style.space(8)

  readonly property var h: service && service.header ? service.header : ({})
  readonly property var targets: {
    if (step === "kept") {
      var out = [thinningSwitch]
      for (var i = 0; i < keptRepeater.count; i++) out.push(keptRepeater.itemAt(i))
      return out
    }
    if (step === "yourBackup") return confirming ? [yesStartOver, cancelStartOver] : [password, startOver]
    return []
  }
  function cursorOn(item) { return panel && panel.cursorTarget === item }

  // --- Restore points: smart thinning, and the kept ones (D35) -----------------------------
  SwitchRow {
    id: thinningSwitch
    visible: page.step === "kept"
    title: "Smart thinning"
    checked: !!page.service && page.service.settings["thinning.on"] !== false
    hasCursorHere: page.cursorOn(this)
    // The rules are backup/thinning.py's: keep these words in step with it.
    explainer: checked
      ? "Thins out old restore points as they age. It keeps:\n"
        + "·  every backup from the last 24 hours\n"
        + "·  one a day for the 30 days before that\n"
        + "·  one a week after that, for as long as there's room\n"
        + "Backing up every hour, that's about 100 restore points after a year. Kept ones are never thinned."
      : "Off: nothing is ever deleted by itself. Every backup stays a restore point (24 a day, backing "
        + "up every hour). When your backup is full, backups stop and say so: turn this back on, or "
        + "delete restore points you don't need."
    onToggled: page.service.setSetting("thinning.on", !checked)
  }
  PanelSectionHeader { visible: page.step === "kept"; text: "Select restore points to keep" }
  Prose {
    visible: page.step === "kept"
    width: parent.width
    dim: true
    text: "A kept restore point is never thinned or deleted, so you can always go back to it."
  }
  Repeater {
    id: keptRepeater
    model: page.step === "kept" && page.service ? page.service.points : []
    SwitchRow {
      required property var modelData
      title: Model.capital(Model.when(modelData.when))
      explainer: modelData.return_point ? "The Return point (from before a handover)." : ""
      checked: modelData.kept || modelData.return_point
      hasCursorHere: page.cursorOn(this)
      onToggled: page.service.keep(modelData.name, !checked)
    }
  }

  // --- Your backup ------------------------------------------------------------------------
  Column {
    visible: page.step === "yourBackup"
    width: parent.width
    spacing: Style.space(6)
    Prose {
      width: parent.width
      text: page.h.kind === "disk" ? "The backup disk " + (page.h.model || "plugged in here")
                                   : "Your backup server, " + (page.h.address || "")
    }
    Prose {
      width: parent.width
      dim: true
      text: "Size " + Model.human(page.h.size)
            + (page.h.space && page.h.space.used ? " · used " + Model.human(page.h.space.used) : "")
            + (page.h.space && page.h.space.free ? " · free " + Model.human(page.h.space.free) : "")
    }
    Prose {
      width: parent.width
      dim: true
      text: (page.h.points_count || 0) + " restore points"
            + (page.service && page.service.points.length ? ", the oldest from "
               + Model.when(page.service.points[page.service.points.length - 1].when) : "")
    }
    NavRow {
      id: password
      visible: !page.confirming
      title: "Change its password"
      explainer: "In a terminal window: your backup's current password, then the new one."
      hasCursorHere: page.cursorOn(this)
      onActivated: page.service.changePassword()
    }
    NavRow {
      id: startOver
      visible: !page.confirming
      title: "Start over"
      explainer: "This computer forgets where it backs up, and you set backups up again. "
                 + "Your backup isn't deleted: it stays where it is, with all its restore points."
      hasCursorHere: page.cursorOn(this)
      onActivated: page.confirming = true
    }
    Prose {
      visible: page.confirming
      width: parent.width
      text: "Start over? This computer forgets where it backs up. Your backup isn't deleted: "
            + "it stays where it is, with all its restore points."
    }
    Row {
      visible: page.confirming
      spacing: Style.space(8)
      ActionButton {
        id: yesStartOver
        text: "Yes, start over"
        hasCursorHere: page.cursorOn(this)
        onClicked: { page.confirming = false; page.service.startOver(); page.panel.go("") }
      }
      ActionButton {
        id: cancelStartOver
        text: "Cancel"
        hasCursorHere: page.cursorOn(this)
        onClicked: page.confirming = false
      }
    }
  }
}
