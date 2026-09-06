import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons

BarWidget {
  id: root
  moduleName: "ok-extras.apps"
  property var usage: ({})
  property var allowlist: ({})
  property double now: Date.now()
  readonly property bool stale: !usage.updated_at || now - Date.parse(usage.updated_at) > 15000
  readonly property var definitions: [
    { app: "digger", title: "Digger", key: "digger_remaining_seconds" },
    { app: "micropolis", title: "Micropolis", key: "micropolis_remaining_seconds" },
    { app: "minecraft", title: "Games", key: "remaining_seconds" },
    { app: "stardew_valley", title: "Games", key: "remaining_seconds" },
    { app: "vlc", title: "Videos", key: "vlc_remaining_seconds" }
  ]
  readonly property var entries: {
    var enabled = usage.enabled_apps || (allowlist.games || []).concat(allowlist.videos || [])
    var seenGames = false
    return definitions.filter(function(entry) {
      if (enabled.indexOf(entry.app) < 0) return false
      if (entry.title === "Games") {
        if (seenGames) return false
        seenGames = true
      }
      return true
    })
  }
  implicitWidth: vertical ? barSize : row.implicitWidth + 12
  implicitHeight: vertical ? row.implicitHeight : barSize

  function decode(raw) {
    try { return JSON.parse(raw) } catch (e) { return {} }
  }
  function timeLabel(seconds) {
    var s = Math.max(0, Math.floor(Number(seconds) || 0))
    return Math.floor(s / 60) + ":" + (s % 60 < 10 ? "0" : "") + s % 60
  }
  FileView {
    id: stateFile
    path: "/var/lib/omarchy-kids/usage.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.usage = root.decode(text())
    onFileChanged: reload()
  }
  FileView {
    path: "/etc/omarchy-kids/allowlist.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.allowlist = root.decode(text())
    onFileChanged: reload()
  }
  Timer {
    interval: 1000
    running: true
    repeat: true
    onTriggered: root.now = Date.now()
  }
  Row {
    id: row
    anchors.centerIn: parent
    spacing: 12
    Repeater {
      model: root.entries
      delegate: Text {
        required property var modelData
        readonly property var status: root.usage.app_status ? root.usage.app_status[modelData.app] : null
        readonly property bool blocked: status ? status.blocked : Number(root.usage[modelData.key]) <= 0
        text: modelData.title + " " + (root.stale ? "—" : root.timeLabel(root.usage[modelData.key]))
        color: blocked && !root.stale ? "#ff806e" : (root.bar ? root.bar.barForeground : Color.foreground)
        font.family: root.bar ? root.bar.fontFamily : Style.font.family
        font.pixelSize: Style.font.body
        MouseArea {
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: Quickshell.execDetached(["/usr/bin/omarchy-kids-ui", "--app", modelData.app])
          onEntered: if (root.bar) root.bar.showTooltip(root, modelData.title + " allowance · click for extra time")
          onExited: if (root.bar) root.bar.hideTooltip(root)
        }
      }
    }
  }
}
