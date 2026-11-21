// Narrow host-value regression for SDK trade-route presentation callbacks.
// It exercises owned snapshots only; it does not load GameCore or render routes.
#include "TradeRoutePresentation.h"

#include <array>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <string>

using namespace ZeroSisHost;

static unsigned checks = 0;
static void Check(bool value, const char* expression, int line) {
    ++checks;
    if (!value) {
        std::fprintf(stderr, "FAILED line=%d %s\n", line, expression);
        std::exit(1);
    }
}
#define CHECK(value) Check((value), #value, __LINE__)

template<class Exception, class Operation>
static void Throws(Operation operation) {
    bool rejected = false;
    try { operation(); }
    catch (const Exception&) { rejected = true; }
    CHECK(rejected);
}

int main() {
    TradeRoutePresentation routes;
    CHECK(routes.Routes().empty());
    CHECK(!routes.HasPopup() && routes.PopupRoute() == -1);

    // CvGameTrade::MoveUnit emits this before CvPlayerTrade emits NewRoute.
    routes.UpdateDirection(7, true);
    CHECK(routes.Routes().count(7) == 1);
    CHECK(routes.Routes().at(7).plots.empty());
    CHECK(routes.Routes().at(7).directionKnown && routes.Routes().at(7).forwards);

    int x[] = {2, 5, 8};
    int y[] = {3, 6, 9};
    routes.NewRoute(7, 1, TRADE_CONNECTION_INTERNATIONAL, 3, x, y);
    x[0] = 99; y[0] = 99;
    const auto& created = routes.Routes().at(7);
    CHECK(created.player == 1 && created.type == TRADE_CONNECTION_INTERNATIONAL);
    CHECK(created.plots.size() == 3 && created.plots[0].x == 2 && created.plots[0].y == 3);
    CHECK(created.directionKnown && created.forwards);

    // Later movement updates and the save-restore NewRoute -> Update sequence.
    routes.UpdateDirection(7, false);
    CHECK(!routes.Routes().at(7).forwards);
    routes.NewRoute(8, 2, TRADE_CONNECTION_FOOD, 2, x, y);
    CHECK(!routes.Routes().at(8).directionKnown);
    routes.UpdateDirection(8, true);
    CHECK(routes.Routes().at(8).directionKnown && routes.Routes().at(8).forwards);

    routes.ActivatePopup(7);
    CHECK(routes.HasPopup() && routes.PopupRoute() == 7);
    routes.ActivatePopup(8);
    CHECK(routes.HasPopup() && routes.PopupRoute() == 8);
    routes.DeactivatePopup();
    CHECK(!routes.HasPopup() && routes.PopupRoute() == -1);

    // Failed replacements must not corrupt the last complete route snapshot.
    routes.ActivatePopup(7);
    const std::string beforeInvalid = routes.SnapshotJson();
    Throws<std::invalid_argument>([&] { routes.NewRoute(-2, 1, TRADE_CONNECTION_INTERNATIONAL, 1, x, y); });
    Throws<std::invalid_argument>([&] { routes.NewRoute(7, MAX_PLAYERS, TRADE_CONNECTION_INTERNATIONAL, 1, x, y); });
    Throws<std::invalid_argument>([&] { routes.NewRoute(7, 1, static_cast<TradeConnectionType>(-1), 1, x, y); });
    Throws<std::invalid_argument>([&] { routes.NewRoute(7, 1, NUM_TRADE_CONNECTION_TYPES, 1, x, y); });
    Throws<std::invalid_argument>([&] { routes.NewRoute(7, 1, TRADE_CONNECTION_INTERNATIONAL, 0, x, y); });
    Throws<std::invalid_argument>([&] { routes.NewRoute(7, 1, TRADE_CONNECTION_INTERNATIONAL, 257, x, y); });
    Throws<std::invalid_argument>([&] { routes.NewRoute(7, 1, TRADE_CONNECTION_INTERNATIONAL, 1, nullptr, y); });
    Throws<std::invalid_argument>([&] { routes.NewRoute(7, 1, TRADE_CONNECTION_INTERNATIONAL, 1, x, nullptr); });
    int badX[] = {-1};
    Throws<std::invalid_argument>([&] { routes.NewRoute(7, 1, TRADE_CONNECTION_INTERNATIONAL, 1, badX, y); });
    int badY[] = {4, -1};
    Throws<std::invalid_argument>([&] { routes.NewRoute(7, 1, TRADE_CONNECTION_INTERNATIONAL, 2, x, badY); });
    Throws<std::invalid_argument>([&] { routes.UpdateDirection(-2, true); });
    CHECK(routes.SnapshotJson() == beforeInvalid);

    Throws<std::logic_error>([&] { routes.ActivatePopup(99); });
    CHECK(routes.SnapshotJson() == beforeInvalid);
    Throws<std::invalid_argument>([&] { routes.DestroyRoute(7, 2); });
    CHECK(routes.SnapshotJson() == beforeInvalid);

    // Temporary previews use -1 and are destroyed for the active player,
    // which can differ from their origin owner.
    routes.NewRoute(-1, 3, TRADE_CONNECTION_PRODUCTION, 2, x, y);
    routes.ActivatePopup(-1);
    CHECK(routes.PopupRoute() == -1);
    routes.DestroyRoute(-1, 0);
    CHECK(routes.Routes().count(-1) == 0 && !routes.HasPopup());

    // Destroy clears an active ordinary route; reusing its index cannot inherit
    // stale movement direction from the retired connection.
    routes.ActivatePopup(7);
    routes.DestroyRoute(7, 1);
    CHECK(routes.Routes().count(7) == 0 && !routes.HasPopup());
    routes.NewRoute(7, 1, TRADE_CONNECTION_INTERNATIONAL, 1, x, y);
    CHECK(!routes.Routes().at(7).directionKnown);
    routes.DestroyRoute(7, 1);
    routes.DestroyRoute(123, 0); // unknown SDK route destruction is idempotent
    CHECK(routes.Routes().count(7) == 0);

    routes.NewRoute(9, 2, TRADE_CONNECTION_PRODUCTION, 1, x, y);
    routes.UpdateDirection(9, false); // restored route direction follows NewRoute
    CHECK(routes.Routes().at(9).directionKnown && !routes.Routes().at(9).forwards);
    routes.ActivatePopup(9);
    routes.Clear();
    CHECK(routes.Routes().empty() && !routes.HasPopup() && routes.PopupRoute() == -1);
    CHECK(routes.SnapshotJson().find("\"routes\":[]") != std::string::npos);

    std::printf("TRADE_ROUTE_PRESENTATION_PASS checks=%u GAMECORE_LOADED=false\n", checks);
    return 0;
}
