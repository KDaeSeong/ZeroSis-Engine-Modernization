#pragma once
#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace ZeroSisHost {
struct UiMapMenuFile final {
    std::string path,name,worldType,modificationTime;
    std::uint32_t width=0,height=0,timeHigh=0,timeLow=0;
    std::uint64_t bytes=0;
    std::array<std::uint32_t,3> identity{};
    std::array<unsigned char,32> checksum{};
};
struct UiMapMenuCatalog final {
    std::vector<UiMapMenuFile> files;
    std::string mapScript,worldType;
    std::string parentContext="GameMenu";
    int worldSize=-1;
    std::function<bool(const std::string&)> nameAvailable;
};
struct MapMenuRequest final {
    enum class Kind { Save,Overwrite,Delete };
    Kind kind;int owner=-1,turn=-1;std::string name;
    std::shared_ptr<const UiMapMenuFile> expected;
};
}
