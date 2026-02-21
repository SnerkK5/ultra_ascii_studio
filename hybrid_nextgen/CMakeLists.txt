cmake_minimum_required(VERSION 3.21)
project(UltraAsciiHybrid LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Core Gui Qml Quick)

qt_standard_project_setup(REQUIRES 6.5)

qt_add_executable(ultra_ascii_hybrid
    src/main.cpp
    src/ascii_engine.cpp
    src/ascii_engine.h
)

qt_add_qml_module(ultra_ascii_hybrid
    URI UltraAscii
    VERSION 1.0
    QML_FILES
        qml/main.qml
)

target_link_libraries(ultra_ascii_hybrid PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Qml
    Qt6::Quick
)

install(TARGETS ultra_ascii_hybrid
    RUNTIME DESTINATION .
)
