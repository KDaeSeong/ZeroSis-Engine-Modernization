#pragma once

#include "SdkHostIncludes.h"

#include <CvStructs.h>

#include <array>
#include <cmath>
#include <memory>
#include <stdexcept>
#include <vector>

namespace ZeroSisHost {

// An owned value snapshot of the SDK's transient combat-presentation payload.
// It contains no SDK interface pointers and performs no game-state mutation.
struct CombatPresentation {
    bool cityEvent = false;
    int plotIndex = -1;
    int plotX = -1;
    int plotY = -1;

    bool attackerAdvances = false;
    bool visualize = false;
    bool defenderRetaliates = false;
    bool ranged = false;
    bool bombing = false;
    bool airSweep = false;
    bool defenderCaptured = false;
    int nuclearDamageLevel = 0;

    struct Participant {
        bool hasUnit = false;
        bool hasCity = false;
        int unitOwner = -1;
        int unitId = -1;
        int unitX = -1;
        int unitY = -1;
        int cityOwner = -1;
        int cityId = -1;
        int cityX = -1;
        int cityY = -1;
        int damageInflicted = 0;
        int finalDamage = 0;
    };

    std::array<Participant, BATTLE_UNIT_COUNT> participants{};
    std::vector<CvCombatMemberEntry> damageMembers;

    static CombatPresentation Capture(ICvCombatInfo1* info, bool cityEvent) {
        if (!info) {
            throw std::invalid_argument("Combat presentation requires combat info");
        }

        CombatPresentation snapshot;
        snapshot.cityEvent = cityEvent;

        // GetPlot/GetUnit/GetCity return owned adapter wrappers around borrowed
        // GameCore objects. Keep each wrapper local and retain only scalar data.
        std::unique_ptr<ICvPlot1> plot(info->GetPlot());
        if (!plot) {
            throw std::invalid_argument("Combat presentation requires a target plot");
        }
        snapshot.plotIndex = plot->GetPlotIndex();
        plot->GetPosition(snapshot.plotX, snapshot.plotY);
        if (snapshot.plotIndex < 0) {
            throw std::invalid_argument("Combat presentation target plot has an invalid index");
        }

        snapshot.attackerAdvances = info->GetAttackerAdvances();
        snapshot.visualize = info->GetVisualizeCombat();
        snapshot.defenderRetaliates = info->GetDefenderRetaliates();
        snapshot.ranged = info->GetAttackIsRanged();
        snapshot.bombing = info->GetAttackIsBombingMission();
        snapshot.airSweep = info->GetAttackIsAirSweep();
        snapshot.defenderCaptured = info->GetDefenderCaptured();
        snapshot.nuclearDamageLevel = info->GetNuclearDamageLevel();

        for (int slot = 0; slot < BATTLE_UNIT_COUNT; ++slot) {
            const BattleUnitTypes battleUnit = static_cast<BattleUnitTypes>(slot);
            Participant& participant = snapshot.participants[static_cast<std::size_t>(slot)];

            std::unique_ptr<ICvUnit1> unit(info->GetUnit(battleUnit));
            if (unit) {
                participant.hasUnit = true;
                participant.unitOwner = static_cast<int>(unit->GetOwner());
                participant.unitId = unit->GetID();
                participant.unitX = unit->GetX();
                participant.unitY = unit->GetY();
                if (participant.unitOwner < 0 || participant.unitOwner >= MAX_PLAYERS || participant.unitId < 0) {
                    throw std::invalid_argument("Combat presentation contains an invalid unit identity");
                }
            }

            std::unique_ptr<ICvCity1> city(info->GetCity(battleUnit));
            if (city) {
                participant.hasCity = true;
                participant.cityOwner = static_cast<int>(city->GetOwner());
                participant.cityId = city->GetID();
                participant.cityX = city->GetX();
                participant.cityY = city->GetY();
                if (participant.cityOwner < 0 || participant.cityOwner >= MAX_PLAYERS || participant.cityId < 0) {
                    throw std::invalid_argument("Combat presentation contains an invalid city identity");
                }
            }

            participant.damageInflicted = info->GetDamageInflicted(battleUnit);
            participant.finalDamage = info->GetFinalDamage(battleUnit);
        }

        const int damageMemberCount = info->GetDamageMemberCount();
        const int maxDamageMemberCount = info->GetMaxDamageMemberCount();
        if (damageMemberCount < 0 || maxDamageMemberCount < 0 ||
            damageMemberCount > maxDamageMemberCount || maxDamageMemberCount > MAX_DAMAGE_MEMBER_COUNT) {
            throw std::invalid_argument("Combat presentation damage-member counts are outside SDK bounds");
        }

        snapshot.damageMembers.reserve(static_cast<std::size_t>(damageMemberCount));
        for (int index = 0; index < damageMemberCount; ++index) {
            // GetDamageMember is a borrowed pointer into the caller's transient
            // CvCombatInfo; copy it while the callback is still on the stack.
            const CvCombatMemberEntry* const member = info->GetDamageMember(index);
            if (!member) {
                throw std::invalid_argument("Combat presentation has a missing active damage member");
            }
            if (member->GetPlayer() < 0 || member->GetPlayer() >= MAX_PLAYERS || member->GetID() < 0) {
                throw std::invalid_argument("Combat presentation has an invalid damage-member identity");
            }
            if (!std::isfinite(member->m_fWeaponOption)) {
                throw std::invalid_argument("Combat presentation has a non-finite damage-member weapon option");
            }
            snapshot.damageMembers.push_back(*member);
        }

        return snapshot;
    }
};

} // namespace ZeroSisHost
