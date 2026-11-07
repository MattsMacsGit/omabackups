import QtQuick
import qs.Commons
import qs.Ui
import "../parts"
import "../Model.js" as Model

// Settings (BUILD 6.1 E, 7.1). Switches are real switches; a gear
// only shows that switch's own options (1.x rule).
Column {
  id: page
  property var service: null
  property var panel: null
  spacing: Style.space(8)

  readonly property var s: service ? service.settings : ({})
  // The cursor's path, top to bottom; an open gear's options come right after its switch.
  readonly property var targets: [pick, automatic].concat(items(automatic.gearOpen ? everyRepeater : null),
                                   [awayMinus, awayPlus, health],
                                   health.gearOpen ? [atMinus, atPlus].concat(items(minutesRepeater)) : [],
                                   [kept, changes, yourBackup])
  function items(repeater) {
    var out = []
    for (var i = 0; repeater && i < repeater.count; i++) out.push(repeater.itemAt(i))
    return out
  }
  function cursorOn(item) { return panel && panel.cursorTarget === item }
  function set(name, value) { service.setSetting(name, value) }

  NavRow {
    id: pick
    title: "Choose what gets backed up"
    explainer: "Opens the picker in a terminal window."
    hasCursorHere: page.cursorOn(this)
    onActivated: page.service.pick()
  }

  SwitchRow {
    id: automatic
    title: "Automatic backups"
    checked: page.s["automatic.on"] === true
    hasGear: true
    hasCursorHere: page.cursorOn(this)
    explainer: checked ? ({ hourly: "Every hour.", daily: "Once a day.", weekly: "Once a week." })[page.s["automatic.every"]] || ""
                       : "Off: only Back up now backs up."
    onToggled: page.set("automatic.on", !checked)
    options: Row {
      spacing: Style.space(6)
      Repeater {
        id: everyRepeater
        model: [["hourly", "Every hour"], ["daily", "Every day"], ["weekly", "Every week"]]
        OptionButton {
          required property var modelData
          owner: page
          text: modelData[1]
          selected: page.s["automatic.every"] === modelData[0]
          onClicked: page.set("automatic.every", modelData[0])
        }
      }
    }
  }

  Item {
    id: away
    width: parent.width
    implicitHeight: awayColumn.implicitHeight + Style.space(14)
    Column {
      id: awayColumn
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.margins: Style.space(10)
      spacing: Style.space(4)
      Prose { width: parent.width; text: "Away from home" }
      Row {
        spacing: Style.space(8)
        Prose { anchors.verticalCenter: parent.verticalCenter; dim: true; wrapMode: Text.NoWrap; text: "Ask first above" }
        OptionButton { id: awayMinus; owner: page; text: "−"; onClicked: page.set("away.limit_mb", Math.max(50, (page.s["away.limit_mb"] || 500) - 100)) }
        Prose { anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.NoWrap; text: (page.s["away.limit_mb"] || 500) + " MB" }
        OptionButton { id: awayPlus; owner: page; text: "+"; onClicked: page.set("away.limit_mb", (page.s["away.limit_mb"] || 500) + 100) }
      }
      Prose { width: parent.width; dim: true; text: "Away from home, a backup bigger than this asks first: it counts against your data." }
    }
  }

  SwitchRow {
    id: health
    title: "Health check"
    checked: page.s["health.on"] === true
    hasGear: true
    hasCursorHere: page.cursorOn(this)
    explainer: checked ? "Each night at " + Model.clock(new Date(2000, 0, 1, page.s["health.at"] || 0)).replace(":00", "")
                         + ", for up to " + ((page.s["health.minutes"] || 120) >= 60 ? (page.s["health.minutes"] / 60) + " hour"
                         + (page.s["health.minutes"] > 60 ? "s" : "") : page.s["health.minutes"] + " minutes") + ". You only hear about it if something's wrong."
                       : "Off: your backup isn't checked."
    onToggled: page.set("health.on", !checked)
    options: Column {
      spacing: Style.space(6)
      Row {
        spacing: Style.space(8)
        Prose { anchors.verticalCenter: parent.verticalCenter; dim: true; wrapMode: Text.NoWrap; text: "Starts at" }
        OptionButton { id: atMinus; owner: page; text: "−"; onClicked: page.set("health.at", ((page.s["health.at"] || 0) + 23) % 24) }
        Prose { anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.NoWrap; text: Model.clock(new Date(2000, 0, 1, page.s["health.at"] || 0)) }
        OptionButton { id: atPlus; owner: page; text: "+"; onClicked: page.set("health.at", ((page.s["health.at"] || 0) + 1) % 24) }
      }
      Row {
        spacing: Style.space(6)
        Repeater {
          id: minutesRepeater
          model: [30, 60, 120, 240, 480]
          OptionButton {
            required property var modelData
            owner: page
            text: modelData < 60 ? modelData + " min" : (modelData / 60) + " h"
            selected: page.s["health.minutes"] === modelData
            onClicked: page.set("health.minutes", modelData)
          }
        }
      }
    }
  }

  NavRow {
    id: kept
    title: "Kept restore points"
    explainer: "Never thinned or deleted. " + (page.service ? page.service.status.kept ? page.service.status.kept.length : 0 : 0) + " kept."
    hasCursorHere: page.cursorOn(this)
    onActivated: page.panel.go("kept")
  }

  NavRow {
    id: changes
    title: "Your changes to Omarchy"
    explainer: page.service && page.service.header && page.service.header.last_finished
               ? "Latest backup was " + Model.when(page.service.header.last_finished) : "Made with your first backup."
    hasCursorHere: page.cursorOn(this)
    onActivated: { page.service.loadChanges(); page.panel.go("changes") }
  }

  NavRow {
    id: yourBackup
    title: "Your backup"
    explainer: page.service && page.service.header
               ? (page.service.header.kind === "disk" ? "Backup disk" : "Backup server") + " · "
                 + Model.human(page.service.header.size) + (page.service.header.space && page.service.header.space.free
                 ? " · " + Model.human(page.service.header.space.free) + " free" : "")
               : ""
    hasCursorHere: page.cursorOn(this)
    onActivated: page.panel.go("yourBackup")
  }

  NavRow {
    title: "Rescue USB"
    explainer: "Make / Refresh Rescue USB comes with a later version."
    enabledRow: false
  }
}
