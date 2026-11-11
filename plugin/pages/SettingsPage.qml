import QtQuick
import qs.Commons
import qs.Ui
import "../parts"
import "../Model.js" as Model

// Settings (BUILD 6.1 E, 7.1, D32). Every row is one big button; switches
// flip from anywhere on their row, and a gear at the far end shows only that
// switch's own options, as labelled choices (1.x).
Column {
  id: page
  property var service: null
  property var panel: null
  spacing: Style.space(6)

  readonly property var s: service ? service.settings : ({})
  // The cursor's path, top to bottom; an open gear's options come right after its switch.
  readonly property var targets: [pick, automatic].concat(
      automatic.gearShown && automatic.gearOpen ? every.buttons : [],
      [health],
      health.gearShown && health.gearOpen ? startAt.buttons.concat(howLong.buttons) : [],
      [away],
      away.gearShown && away.gearOpen ? awayLimit.buttons : [],
      [points, yourBackup, rescue])
  function cursorOn(item) { return panel && panel.cursorTarget === item }
  function set(name, value) { service.setSetting(name, value) }

  readonly property var hours: [[22, "10 pm"], [0, "Midnight"], [2, "2 am"], [4, "4 am"]]
  readonly property var limits: [[100, "100 MB"], [250, "250 MB"], [500, "500 MB"], [1000, "1 GB"], [2000, "2 GB"]]
  readonly property var lengths: [[60, "1 hour"], [120, "2 hours"], [240, "4 hours"]]
  function label(list, value, fallback) {
    var found = list.filter(function(c) { return c[0] === value })
    return found.length ? found[0][1] : fallback
  }

  NavRow {
    id: pick
    title: "Choose what gets backed up"
    explainer: "Opens the file selection window to make your choices."
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
    options: Choices {
      id: every
      owner: page
      label: "How often"
      model: [["hourly", "Every hour"], ["daily", "Every day"], ["weekly", "Every week"]]
      value: page.s["automatic.every"]
      onChosen: function(v) { page.set("automatic.every", v) }
    }
  }

  SwitchRow {
    id: health
    title: "Nightly health check"
    checked: page.s["health.on"] === true
    hasGear: true
    hasCursorHere: page.cursorOn(this)
    explainer: checked
      ? "Each night from " + page.label(page.hours, page.s["health.at"], "midnight").toLowerCase()
        + ", for up to " + page.label(page.lengths, page.s["health.minutes"], (page.s["health.minutes"] || 120) + " minutes")
        + ". You only hear about it if something's wrong."
      : "Off: damage in your backup would only be found when you restore."
    onToggled: page.set("health.on", !checked)
    options: Column {
      width: parent ? parent.width : 300
      spacing: Style.space(8)
      Choices {
        id: startAt
        owner: page
        label: "Start at"
        model: page.hours
        value: page.s["health.at"]
        onChosen: function(v) { page.set("health.at", v) }
      }
      Choices {
        id: howLong
        owner: page
        label: "Check for up to, each night"
        model: page.lengths
        value: page.s["health.minutes"]
        onChosen: function(v) { page.set("health.minutes", v) }
      }
    }
  }

  SwitchRow {
    id: away
    title: "Away from home"
    checked: page.s["away.on"] !== false
    hasGear: true
    hasCursorHere: page.cursorOn(this)
    explainer: checked
      ? "When you're away (over Tailscale, or any network your backup server isn't on), a backup "
        + "bigger than " + page.label(page.limits, page.s["away.limit_mb"], (page.s["away.limit_mb"] || 500) + " MB")
        + " asks first. Useful on slow or metered connections."
      : "Off: backups never ask first, whatever network you're on."
    onToggled: page.set("away.on", !checked)
    options: Choices {
      id: awayLimit
      owner: page
      label: "Ask first above"
      model: page.limits
      value: page.s["away.limit_mb"]
      onChosen: function(v) { page.set("away.limit_mb", v) }
    }
  }

  NavRow {
    id: points
    title: "Restore points"
    explainer: "Smart thinning " + (page.s["thinning.on"] === false ? "off" : "on") + " · "
               + (page.service && page.service.status.kept ? page.service.status.kept.length : 0) + " kept"
    hasCursorHere: page.cursorOn(this)
    onActivated: page.panel.go("kept")
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
    id: rescue
    readonly property var made: page.service ? page.service.status.rescue_usb : null
    title: made ? "Refresh Rescue USB" : "Make Rescue USB"
    explainer: made
      ? "Your stick, up to date: only its small settings part is rewritten (seconds), and a newer "
        + "rescue system is offered if there is one."
      : "A USB stick that brings this computer back if it won't start. The rescue system downloads "
        + "once (about 1 GB); any stick of 4 GB or more."
    hasCursorHere: page.cursorOn(this)
    onActivated: made ? page.service.rescueRefresh() : page.service.rescueMake()
  }
}
