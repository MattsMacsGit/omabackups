import QtQuick
import qs.Commons
import qs.Ui

// A labelled row of choices (1.x): "Start at" · [10 pm] [Midnight] [2 am].
// The chosen one is shown selected; the keyboard reaches each button.
Column {
  id: choices
  property string label: ""
  property var model: []              // [[value, "label"], ...]
  property var value: null
  property var owner: null            // the page, for its keyboard cursor
  signal chosen(var value)
  width: parent ? parent.width : 300
  spacing: Style.space(4)

  readonly property var buttons: {
    var out = []
    for (var i = 0; i < repeater.count; i++) out.push(repeater.itemAt(i))
    return out
  }

  Prose { visible: text !== ""; width: parent.width; dim: true; text: choices.label }
  Flow {
    width: parent.width
    spacing: Style.space(6)
    Repeater {
      id: repeater
      model: choices.model
      OptionButton {
        required property var modelData
        owner: choices.owner
        text: modelData[1]
        selected: choices.value === modelData[0]
        onClicked: choices.chosen(modelData[0])
      }
    }
  }
}
