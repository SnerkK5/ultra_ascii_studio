#include <QCoreApplication>
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>

#include "ascii_engine.h"

int main(int argc, char* argv[]) {
    QGuiApplication app(argc, argv);

    QString bridgeFile;
    const QStringList args = app.arguments();
    for (int i = 1; i < args.size(); ++i) {
        if (args[i] == "--bridge-file" && i + 1 < args.size()) {
            bridgeFile = args[i + 1];
            ++i;
        }
    }

    QQmlApplicationEngine engine;
    AsciiEngine asciiEngine;

    if (!bridgeFile.trimmed().isEmpty()) {
        asciiEngine.setBridgeFile(bridgeFile);
        asciiEngine.loadBridge();
    }

    QObject::connect(&app, &QCoreApplication::aboutToQuit, [&asciiEngine]() {
        asciiEngine.saveBridge();
    });

    engine.rootContext()->setContextProperty("asciiEngine", &asciiEngine);

    const QUrl url(QStringLiteral("qrc:/qt/qml/UltraAscii/qml/main.qml"));
    QObject::connect(
        &engine,
        &QQmlApplicationEngine::objectCreationFailed,
        &app,
        []() { QCoreApplication::exit(-1); },
        Qt::QueuedConnection
    );
    engine.load(url);

    return app.exec();
}
