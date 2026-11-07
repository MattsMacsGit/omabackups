import QtQuick
import qs.Commons
import qs.Ui

// A button that also works with the keyboard cursor.
Button {
  property bool hasCursorHere: false
  hasCursor: hasCursorHere
  bordered: true
  function activate() { clicked() }
}
