#include "ascii_engine.h"

#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSet>

AsciiEngine::AsciiEngine(QObject* parent)
    : QObject(parent) {}

bool AsciiEngine::realtimePreview() const {
    return m_realtimePreview;
}

void AsciiEngine::setRealtimePreview(bool v) {
    if (m_realtimePreview == v) {
        return;
    }
    m_realtimePreview = v;
    emit realtimePreviewChanged();
}

int AsciiEngine::timelineMs() const {
    return m_timelineMs;
}

void AsciiEngine::setTimelineMs(int ms) {
    const int clamped = qBound(0, ms, m_durationMs);
    if (m_timelineMs == clamped) {
        return;
    }
    m_timelineMs = clamped;
    emit timelineMsChanged();
}

int AsciiEngine::durationMs() const {
    return m_durationMs;
}

void AsciiEngine::setDurationMs(int ms) {
    const int clamped = qMax(1000, ms);
    if (m_durationMs == clamped) {
        return;
    }
    m_durationMs = clamped;
    if (m_timelineMs > m_durationMs) {
        m_timelineMs = m_durationMs;
        emit timelineMsChanged();
    }
    emit durationMsChanged();
}

QString AsciiEngine::bridgeFile() const {
    return m_bridgeFile;
}

void AsciiEngine::setBridgeFile(const QString& path) {
    const QString p = path.trimmed();
    if (m_bridgeFile == p) {
        return;
    }
    m_bridgeFile = p;
    emit bridgeFileChanged();
}

bool AsciiEngine::typesCompatible(const QString& outType, const QString& inType) const {
    const QString a = outType.trimmed().toLower();
    const QString b = inType.trimmed().toLower();
    if (a == "any" || b == "any") {
        return true;
    }
    return a == b;
}

void AsciiEngine::addNode(const QString& id, const QString& inType, const QString& outType) {
    Node node;
    node.id = id.trimmed();
    node.inType = inType.trimmed().isEmpty() ? "video" : inType.trimmed().toLower();
    node.outType = outType.trimmed().isEmpty() ? "video" : outType.trimmed().toLower();
    m_nodes.push_back(node);
    emit nodeGraphChanged();
}

void AsciiEngine::connectNodes(int src, int dst, int outPort, int inPort) {
    if (src < 0 || dst < 0 || src >= m_nodes.size() || dst >= m_nodes.size() || src == dst) {
        return;
    }
    if (!typesCompatible(m_nodes[src].outType, m_nodes[dst].inType)) {
        emit nodeConnectionRejected(QStringLiteral("Incompatible ports: %1 -> %2").arg(m_nodes[src].outType, m_nodes[dst].inType));
        return;
    }
    for (const Link& l : m_links) {
        if (l.src == src && l.dst == dst && l.outPort == outPort && l.inPort == inPort) {
            return;
        }
    }
    Link link;
    link.src = src;
    link.dst = dst;
    link.outPort = qMax(0, outPort);
    link.inPort = qMax(0, inPort);
    m_links.push_back(link);
    emit nodeGraphChanged();
}

void AsciiEngine::removeNode(int idx) {
    if (idx < 0 || idx >= m_nodes.size()) {
        return;
    }
    m_nodes.removeAt(idx);

    QList<Link> rebuilt;
    for (const Link& l : m_links) {
        if (l.src == idx || l.dst == idx) {
            continue;
        }
        Link n = l;
        if (n.src > idx) {
            --n.src;
        }
        if (n.dst > idx) {
            --n.dst;
        }
        rebuilt.push_back(n);
    }
    m_links = rebuilt;
    emit nodeGraphChanged();
}

QVariantList AsciiEngine::nodeGraph() const {
    QVariantList out;
    for (int i = 0; i < m_nodes.size(); ++i) {
        QVariantMap n;
        n.insert("index", i);
        n.insert("id", m_nodes[i].id);
        n.insert("inType", m_nodes[i].inType);
        n.insert("outType", m_nodes[i].outType);
        out.push_back(n);
    }
    return out;
}

bool AsciiEngine::loadBridge(const QString& path) {
    const QString p = path.trimmed().isEmpty() ? m_bridgeFile : path.trimmed();
    if (p.isEmpty()) {
        return false;
    }
    QFile f(p);
    if (!f.open(QIODevice::ReadOnly)) {
        return false;
    }
    const QJsonDocument doc = QJsonDocument::fromJson(f.readAll());
    f.close();
    if (!doc.isObject()) {
        return false;
    }
    const QJsonObject root = doc.object();
    const QJsonObject bridge = root.contains("bridge_state") && root.value("bridge_state").isObject()
        ? root.value("bridge_state").toObject()
        : root;

    if (bridge.contains("realtime_preview")) {
        setRealtimePreview(bridge.value("realtime_preview").toBool(true));
    }
    if (bridge.contains("timeline_ms")) {
        setTimelineMs(bridge.value("timeline_ms").toInt(0));
    }
    if (bridge.contains("duration_ms")) {
        setDurationMs(bridge.value("duration_ms").toInt(6000));
    }

    QList<Node> nodes;
    if (bridge.contains("nodes") && bridge.value("nodes").isArray()) {
        const QJsonArray arr = bridge.value("nodes").toArray();
        for (const QJsonValue& v : arr) {
            if (!v.isObject()) {
                continue;
            }
            const QJsonObject o = v.toObject();
            Node n;
            n.id = o.value("id").toString().trimmed();
            n.inType = o.value("inType").toString("video").trimmed().toLower();
            n.outType = o.value("outType").toString("video").trimmed().toLower();
            if (n.id.isEmpty()) {
                continue;
            }
            nodes.push_back(n);
        }
    }

    QList<Link> links;
    if (bridge.contains("links") && bridge.value("links").isArray()) {
        const QJsonArray arr = bridge.value("links").toArray();
        for (const QJsonValue& v : arr) {
            if (!v.isObject()) {
                continue;
            }
            const QJsonObject o = v.toObject();
            Link l;
            l.src = o.value("src").toInt(-1);
            l.dst = o.value("dst").toInt(-1);
            l.outPort = qMax(0, o.value("outPort").toInt(0));
            l.inPort = qMax(0, o.value("inPort").toInt(0));
            if (l.src < 0 || l.dst < 0 || l.src >= nodes.size() || l.dst >= nodes.size() || l.src == l.dst) {
                continue;
            }
            if (!typesCompatible(nodes[l.src].outType, nodes[l.dst].inType)) {
                continue;
            }
            links.push_back(l);
        }
    }

    m_nodes = nodes;
    m_links = links;
    emit nodeGraphChanged();
    return true;
}

bool AsciiEngine::saveBridge(const QString& path) const {
    const QString p = path.trimmed().isEmpty() ? m_bridgeFile : path.trimmed();
    if (p.isEmpty()) {
        return false;
    }
    QJsonObject bridge;
    bridge.insert("realtime_preview", m_realtimePreview);
    bridge.insert("timeline_ms", m_timelineMs);
    bridge.insert("duration_ms", m_durationMs);

    QJsonArray nodes;
    for (const Node& n : m_nodes) {
        QJsonObject o;
        o.insert("id", n.id);
        o.insert("inType", n.inType);
        o.insert("outType", n.outType);
        nodes.push_back(o);
    }
    bridge.insert("nodes", nodes);

    QJsonArray links;
    for (const Link& l : m_links) {
        QJsonObject o;
        o.insert("src", l.src);
        o.insert("dst", l.dst);
        o.insert("outPort", l.outPort);
        o.insert("inPort", l.inPort);
        links.push_back(o);
    }
    bridge.insert("links", links);

    QJsonObject root;
    root.insert("bridge_state", bridge);
    const QJsonDocument doc(root);

    QFile f(p);
    if (!f.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        return false;
    }
    const qint64 written = f.write(doc.toJson(QJsonDocument::Indented));
    f.close();
    return written > 0;
}
