import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: win
    width: 1680
    height: 960
    visible: true
    title: "Ultra ASCII Hybrid (QML + C++)"
    color: "#0a111a"

    property int activeTool: 0 // 0 select, 1 razor, 2 trim, 3 ripple

    palette {
        window: "#0a111a"
        base: "#0d1826"
        button: "#17293f"
        buttonText: "#e9f2ff"
        text: "#e9f2ff"
        highlight: "#4fa2ff"
    }

    Behavior on color {
        ColorAnimation { duration: 240 }
    }

    Rectangle {
        id: topBar
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 54
        radius: 12
        anchors.margins: 8
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#11253d" }
            GradientStop { position: 1.0; color: "#0d1a2b" }
        }
        border.color: "#2d527c"

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            spacing: 10
            Label { text: "ISCII Studio"; font.pixelSize: 18; font.bold: true; color: "#f5fbff" }
            Label { text: "Hybrid UI"; color: "#8bb6df" }
            Item { Layout.fillWidth: true }
            Switch {
                id: rtSwitch
                text: "Realtime"
                checked: asciiEngine.realtimePreview
                onToggled: asciiEngine.realtimePreview = checked
            }
            Button {
                text: "Node Workspace"
                onClicked: nodeWorkspace.visible = !nodeWorkspace.visible
            }
            Button {
                text: "Reload Bridge"
                onClicked: asciiEngine.loadBridge()
            }
            Button {
                text: "Save Bridge"
                onClicked: asciiEngine.saveBridge()
            }
        }
    }

    SplitView {
        id: mainSplit
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: topBar.bottom
        anchors.bottom: timelinePanel.top
        anchors.margins: 8
        orientation: Qt.Horizontal

        Rectangle {
            id: mediaPanel
            SplitView.preferredWidth: 320
            SplitView.minimumWidth: 280
            radius: 12
            color: "#0f1a28"
            border.color: "#284462"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 8
                Label { text: "Media Panel"; color: "#f0f7ff"; font.bold: true }
                TabBar {
                    id: tabs
                    Layout.fillWidth: true
                    TabButton { text: "Media" }
                    TabButton { text: "Audio" }
                    TabButton { text: "Text" }
                    TabButton { text: "Effects" }
                    TabButton { text: "Filters" }
                }
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: 12
                    clip: true
                    delegate: Rectangle {
                        width: ListView.view.width
                        height: 54
                        radius: 8
                        color: index % 2 ? "#142337" : "#172c45"
                        border.color: "#2f5278"
                        Row {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: 8
                            spacing: 8
                            Rectangle { width: 38; height: 38; radius: 6; color: "#264a73" }
                            Column {
                                spacing: 2
                                Text { text: "Asset " + (index + 1); color: "#eaf3ff" }
                                Text { text: "Drag to timeline/node"; color: "#92b0cd"; font.pixelSize: 11 }
                            }
                        }
                    }
                }
            }

            Behavior on opacity { NumberAnimation { duration: 200 } }
        }

        Rectangle {
            id: previewPanel
            SplitView.fillWidth: true
            SplitView.minimumWidth: 560
            radius: 12
            color: "#0c1724"
            border.color: "#2b4d73"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 8

                Label { text: "Preview"; color: "#f0f7ff"; font.bold: true }

                Rectangle {
                    id: previewCanvas
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 10
                    color: "#060d16"
                    border.color: "#355b84"

                    Text {
                        anchors.centerIn: parent
                        text: "Drag/Mask/Crop/Keyframes"
                        color: "#86b0d8"
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Label { text: "Time: " + Math.round(asciiEngine.timelineMs/10)/100 + "s"; color: "#cde0f5" }
                    Slider {
                        Layout.fillWidth: true
                        from: 0
                        to: asciiEngine.durationMs
                        value: asciiEngine.timelineMs
                        onMoved: asciiEngine.timelineMs = value
                    }
                }
            }

            Behavior on opacity { NumberAnimation { duration: 200 } }
        }

        Rectangle {
            id: inspector
            SplitView.preferredWidth: 360
            SplitView.minimumWidth: 300
            radius: 12
            color: "#0f1a28"
            border.color: "#2b4d73"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 8
                Label { text: "Inspector"; color: "#f0f7ff"; font.bold: true }

                GroupBox {
                    title: "Transform"
                    Layout.fillWidth: true
                    ColumnLayout {
                        anchors.fill: parent
                        Slider { Layout.fillWidth: true; from: -1000; to: 1000; value: 0 }
                        Slider { Layout.fillWidth: true; from: 0.1; to: 4.0; value: 1.0 }
                    }
                }

                GroupBox {
                    title: "Animation"
                    Layout.fillWidth: true
                    RowLayout {
                        anchors.fill: parent
                        Button { text: "Set In" }
                        Button { text: "Set Out" }
                        Button { text: "Auto" }
                    }
                }

                GroupBox {
                    title: "Nodes"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6
                        Button {
                            text: "+ Video Node"
                            onClicked: asciiEngine.addNode("brightness-node", "video", "video")
                        }
                        Button {
                            text: "+ Audio Node"
                            onClicked: asciiEngine.addNode("audio-gain", "audio", "audio")
                        }
                        ListView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            model: asciiEngine.nodeGraph()
                            delegate: Rectangle {
                                width: ListView.view.width
                                height: 44
                                radius: 8
                                color: "#172a41"
                                border.color: "#2e5279"
                                Row {
                                    anchors.verticalCenter: parent.verticalCenter
                                    anchors.left: parent.left
                                    anchors.leftMargin: 8
                                    spacing: 8
                                    Text { text: modelData.id; color: "#e8f3ff" }
                                    Text { text: "[" + modelData.inType + "->" + modelData.outType + "]"; color: "#96b6d4" }
                                }
                            }
                        }
                    }
                }
            }

            Behavior on opacity { NumberAnimation { duration: 200 } }
        }
    }

    Rectangle {
        id: timelinePanel
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 8
        height: 210
        radius: 12
        color: "#0d1624"
        border.color: "#2b4d73"

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 8
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Repeater {
                    model: ["Select", "Razor", "Trim", "Ripple"]
                    delegate: Button {
                        required property int index
                        required property string modelData
                        text: modelData
                        checkable: true
                        checked: activeTool === index
                        onClicked: activeTool = index
                        background: Rectangle {
                            radius: 8
                            color: checked ? "#356ca3" : "#1a2c43"
                            border.color: checked ? "#8ec8ff" : "#2f4f75"
                            Behavior on color { ColorAnimation { duration: 140 } }
                        }
                    }
                }
                Item { Layout.fillWidth: true }
                Label {
                    text: ["SELECT","RAZOR","TRIM","RIPPLE"][activeTool]
                    color: "#9fccf6"
                    font.bold: true
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: 10
                color: "#0a111b"
                border.color: "#2b4d73"

                Repeater {
                    model: 3
                    delegate: Rectangle {
                        width: parent.width - 24
                        height: 38
                        x: 12
                        y: 12 + index * 44
                        radius: 8
                        color: index === 0 ? "#205f8f" : "#2a3a4d"
                        border.color: "#5d88b4"

                        Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                        Behavior on width { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

                        Text {
                            anchors.centerIn: parent
                            text: index === 0 ? "Video Track" : index === 1 ? "Overlay Track" : "Audio Track"
                            color: "#e7f2ff"
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        id: nodeWorkspace
        anchors.fill: parent
        visible: false
        color: "#0b121ccc"

        Rectangle {
            anchors.fill: parent
            anchors.margins: 80
            radius: 16
            color: "#08111bcc"
            border.color: "#4f83b7"

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Node Workspace"; color: "#f0f8ff"; font.bold: true; font.pixelSize: 17 }
                    Label { text: "Typed ports: video/audio/data"; color: "#93b4d5" }
                    Item { Layout.fillWidth: true }
                    Button { text: "Close"; onClicked: nodeWorkspace.visible = false }
                }

                Rectangle {
                    id: nodeCanvas
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 12
                    color: "#07101a"
                    border.color: "#3f678f"

                    Canvas {
                        anchors.fill: parent
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.reset()
                            ctx.fillStyle = "#07101a"
                            ctx.fillRect(0, 0, width, height)

                            ctx.strokeStyle = "#1a2d44"
                            for (var x = 0; x < width; x += 36) {
                                ctx.beginPath()
                                ctx.moveTo(x, 0)
                                ctx.lineTo(x, height)
                                ctx.stroke()
                            }
                            for (var y = 0; y < height; y += 36) {
                                ctx.beginPath()
                                ctx.moveTo(0, y)
                                ctx.lineTo(width, y)
                                ctx.stroke()
                            }

                            var graph = asciiEngine.nodeGraph()
                            for (var i = 0; i < graph.length; ++i) {
                                var n = graph[i]
                                var nx = 60 + (i % 5) * 230
                                var ny = 70 + Math.floor(i / 5) * 120
                                ctx.fillStyle = "#1a314d"
                                ctx.strokeStyle = "#72b8ff"
                                ctx.lineWidth = 1.5
                                ctx.fillRect(nx, ny, 180, 76)
                                ctx.strokeRect(nx, ny, 180, 76)

                                ctx.fillStyle = "#e9f4ff"
                                ctx.font = "14px sans-serif"
                                ctx.fillText(n.id, nx + 10, ny + 28)

                                var tint = n.outType === "audio" ? "#7ee890" : n.outType === "data" ? "#ffd187" : "#82d8ff"
                                ctx.fillStyle = tint
                                ctx.beginPath()
                                ctx.arc(nx + 176, ny + 38, 5, 0, Math.PI * 2)
                                ctx.fill()
                            }
                        }

                        Connections {
                            target: asciiEngine
                            function onNodeGraphChanged() { parent.requestPaint() }
                        }
                    }
                }
            }
        }

        Behavior on opacity { NumberAnimation { duration: 180 } }
        opacity: visible ? 1 : 0
    }

    Connections {
        target: asciiEngine
        function onNodeConnectionRejected(reason) {
            toast.text = reason
            toast.visible = true
            toastTimer.restart()
        }
    }

    Rectangle {
        id: toast
        visible: false
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: timelinePanel.top
        anchors.bottomMargin: 12
        radius: 8
        color: "#182b41"
        border.color: "#74b8ff"
        width: Math.max(180, toastText.implicitWidth + 24)
        height: 34
        Text {
            id: toastText
            anchors.centerIn: parent
            text: toast.text
            color: "#eaf5ff"
        }
        property string text: ""
        Behavior on opacity { NumberAnimation { duration: 140 } }
        opacity: visible ? 1 : 0
    }

    Timer {
        id: toastTimer
        interval: 1800
        repeat: false
        onTriggered: toast.visible = false
    }
}
