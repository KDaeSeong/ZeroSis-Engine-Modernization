#pragma once
#include "MenuFrontEndAssets.h"
#include <cmath>

namespace ZeroSisHost {
// Original OptionsMenu GamePanel's L,C stack has Offset380,0 and Padding15.
// V3 records its one visible NoBasicHelp row. Reuse that row's center while
// measuring the newly supported visible children in original XML order.
// The existing32px Button_16 default-size candidate is retained; this does not
// establish the retail native checkbox's implicit size or label metrics.
struct MenuRewardOptionsLayout final {
    using Row=MenuFrontEndAssets::OptionControl;
    bool hasReward=false,hasBasic=false;
    Row reward,basic;
    float stackX=0,stackY=0,stackWidth=0,stackHeight=0;
    static const char* RewardLabelKey(){return "TXT_KEY_OPSCREEN_NO_REWARD_POPUPS";}
    static const char* RewardTooltipKey(){return "TXT_KEY_OPSCREEN_NO_REWARD_POPUPS_TT";}
    static MenuRewardOptionsLayout FromBaseline(const Row& oneBasic,bool rewardSupported,bool basicSupported){
        if(oneBasic.key!=10 || oneBasic.textKey!="TXT_KEY_OPSCREEN_NO_BASIC_HELP" ||
           !std::isfinite(oneBasic.x) || !std::isfinite(oneBasic.y) || oneBasic.width!=32 || oneBasic.height!=32 ||
           oneBasic.x<0 || oneBasic.y<0 || oneBasic.x+oneBasic.width>1920 || oneBasic.y+oneBasic.height>1080)
            throw std::invalid_argument("Reward options require the frozen source-backed checkbox baseline");
        MenuRewardOptionsLayout result;result.hasReward=rewardSupported;result.hasBasic=basicSupported;
        result.basic=oneBasic;result.reward=oneBasic;result.reward.key=17;result.reward.textKey=RewardLabelKey();
        const unsigned count=unsigned(rewardSupported)+unsigned(basicSupported);
        result.stackX=oneBasic.x;result.stackWidth=count?oneBasic.width:0;
        result.stackHeight=count?count*oneBasic.height+(count-1)*15.0f:0;
        result.stackY=oneBasic.y+(oneBasic.height-result.stackHeight)*.5f;
        if(count && (result.stackY<0 || result.stackY+result.stackHeight>1080))
            throw std::invalid_argument("Reward options stack escaped the logical viewport");
        float next=result.stackY;
        if(rewardSupported){result.reward.y=next;next+=oneBasic.height+15;}
        if(basicSupported)result.basic.y=next;
        return result;
    }
    static MenuRewardOptionsLayout At(const MenuFrontEndAssets& assets,bool rewardSupported,bool basicSupported){
        return FromBaseline(assets.OptionsControl("NoBasicHelpCheckbox"),rewardSupported,basicSupported);
    }
};
}
