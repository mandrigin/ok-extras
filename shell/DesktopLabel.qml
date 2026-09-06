import QtQuick
import qs.Ui
import qs.Commons

BarWidget {
  id: root
  moduleName: "ok-extras.desktop-label"
  implicitWidth: label.implicitWidth + 4
  implicitHeight: barSize
  Text {
    id: label
    anchors.centerIn: parent
    text: "Desktop"
    color: root.bar ? root.bar.barForeground : Color.foreground
    font.family: root.bar ? root.bar.fontFamily : Style.font.family
    font.pixelSize: Style.font.body
  }
}
