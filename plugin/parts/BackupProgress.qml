import QtQuick
import qs.Commons
import qs.Commons as Commons
import "../Model.js" as Model

// A running backup (D49): the heading for each step ("Checking home…",
// "Backing up home…"), then the honest bar once the total is known
// (sent of total, the speed, time left once it can be trusted); while it's
// still checking, the line that sweeps back and forth.
Column {
  id: box
  property var running: null
  property color barColour: Commons.Color.accent
  readonly property bool known: !!(running && running.step === "send" && running.total > 0)
  spacing: Style.space(6)

  Prose { width: parent.width; text: Model.doing(box.running) }

  Rectangle {
    id: track
    width: parent.width
    height: Style.space(4)
    radius: height / 2
    color: Qt.darker(Commons.Color.foreground, 3)
    Rectangle {                      // the honest bar
      visible: box.known
      width: track.width * Math.min(1, (box.running && box.running.percent || 0) / 100)
      height: parent.height
      radius: parent.radius
      color: box.barColour
    }
    Rectangle {                      // still checking: no total yet
      id: sweep
      visible: !box.known
      width: parent.width / 4
      height: parent.height
      radius: parent.radius
      color: box.barColour
      SequentialAnimation on x {
        running: sweep.visible && !!box.running && !Style.reduceMotion
        loops: Animation.Infinite
        NumberAnimation { from: 0; to: track.width - sweep.width; duration: Style.duration(1200) }
        NumberAnimation { from: track.width - sweep.width; to: 0; duration: Style.duration(1200) }
      }
    }
  }

  Prose { visible: text !== ""; width: parent.width; dim: true; text: Model.detail(box.running) }
  Prose { visible: text !== ""; width: parent.width; dim: true; text: Model.already(box.running) }
  Prose { visible: text !== ""; width: parent.width; dim: true; text: Model.quiet(box.running) }
}
