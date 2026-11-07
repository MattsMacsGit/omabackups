import QtQuick
import qs.Commons
import qs.Ui
import "../parts"
import "../Model.js" as Model

// Settings' detail pages (BUILD 6.1 E, 7.1): kept restore
// points, Your changes to Omarchy, and Your backup.
Column {
  id: page
  property var service: null
  property var panel: null
  property string step: "kept"          // kept | changes | yourBackup
  property bool confirming: false
  spacing: Style.space(8)

  readonly property var h: service && service.header ? service.header : ({})
  readonly property var targets: {
    if (step === "kept") {
      var out = []
      for (var i = 0; i < keptRepeater.count; i++) out.push(keptRepeater.itemAt(i))
      return out
    }
    if (step === "yourBackup") return confirming ? [yesStartOver, cancelStartOver] : [password, startOver]
    return []
  }
  function cursorOn(item) { return panel && panel.cursorTarget === item }

  // --- Kept restore points ------------------------------------------------------------
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

  // --- Your changes to Omarchy (read only) ---------------------------------------------
  Prose {
    visible: page.step === "changes"
    width: parent.width
    text: "A record, kept with every backup, of what you've added and changed on top of a fresh "
          + "Omarchy: apps, settings, keybindings, your theme. When you move to a new computer, "
          + "Migrate offers to bring all of it over."
  }
  Prose {
    visible: page.step === "changes"
    width: parent.width
    dim: true
    text: page.service && page.service.changes ? "Latest backup was " + Model.when(page.service.changes.made)
                                                 : "Loading…"
  }
  Repeater {
    model: page.step === "changes" && page.service && page.service.changes ? page.service.changes.groups : []
    Column {
      required property var modelData
      readonly property var mine: page.service.changes.items.filter(function(i) { return i.group === modelData.id })
      visible: mine.length > 0
      width: page.width
      spacing: Style.space(4)
      PanelSectionHeader { text: modelData.title + " (" + parent.mine.length + ")" }
      Repeater {
        model: parent.mine
        Column {
          required property var modelData
          width: page.width
          Prose { width: parent.width; text: modelData.name + (modelData.bytes ? "  ·  " + Model.human(modelData.bytes) : "") }
          Prose { width: parent.width; visible: text !== ""; dim: true; text: modelData.what || "" }
        }
      }
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
    ActionButton {
      id: password
      visible: !page.confirming
      text: "Change its password"
      hasCursorHere: page.cursorOn(this)
      onClicked: page.service.changePassword()
    }
    Prose { visible: !page.confirming; width: parent.width; dim: true; text: "In a terminal window: your backup's current password, then the new one." }
    ActionButton {
      id: startOver
      visible: !page.confirming
      text: "Start over"
      hasCursorHere: page.cursorOn(this)
      onClicked: page.confirming = true
    }
    Prose {
      width: parent.width
      dim: !page.confirming
      text: "This computer forgets where it backs up, and you set backups up again. Your backup isn't "
            + "deleted: it stays where it is, with all its restore points."
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
