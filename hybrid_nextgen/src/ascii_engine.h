#pragma once

#include <QObject>
#include <QVariantList>
#include <QString>

class AsciiEngine : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool realtimePreview READ realtimePreview WRITE setRealtimePreview NOTIFY realtimePreviewChanged)
    Q_PROPERTY(int timelineMs READ timelineMs WRITE setTimelineMs NOTIFY timelineMsChanged)
    Q_PROPERTY(int durationMs READ durationMs WRITE setDurationMs NOTIFY durationMsChanged)
    Q_PROPERTY(QString bridgeFile READ bridgeFile WRITE setBridgeFile NOTIFY bridgeFileChanged)

public:
    explicit AsciiEngine(QObject* parent = nullptr);

    bool realtimePreview() const;
    void setRealtimePreview(bool v);

    int timelineMs() const;
    void setTimelineMs(int ms);

    int durationMs() const;
    void setDurationMs(int ms);

    QString bridgeFile() const;
    void setBridgeFile(const QString& path);

    Q_INVOKABLE bool loadBridge(const QString& path = QString());
    Q_INVOKABLE bool saveBridge(const QString& path = QString()) const;

    Q_INVOKABLE void addNode(const QString& id, const QString& inType, const QString& outType);
    Q_INVOKABLE void connectNodes(int src, int dst, int outPort, int inPort);
    Q_INVOKABLE void removeNode(int idx);
    Q_INVOKABLE QVariantList nodeGraph() const;

signals:
    void realtimePreviewChanged();
    void timelineMsChanged();
    void durationMsChanged();
    void bridgeFileChanged();
    void nodeGraphChanged();
    void nodeConnectionRejected(const QString& reason);

private:
    struct Link {
        int src = -1;
        int dst = -1;
        int outPort = 0;
        int inPort = 0;
    };

    struct Node {
        QString id;
        QString inType = "video";
        QString outType = "video";
    };

    bool typesCompatible(const QString& outType, const QString& inType) const;

    bool m_realtimePreview = true;
    int m_timelineMs = 0;
    int m_durationMs = 6000;
    QString m_bridgeFile;
    QList<Node> m_nodes;
    QList<Link> m_links;
};
