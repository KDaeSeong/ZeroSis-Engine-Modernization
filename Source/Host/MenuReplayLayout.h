#pragma once
#include <stdexcept>

namespace ZeroSisHost {
struct MenuReplayBounds final {
    float x=0,y=0,width=0,height=0;
    float Right() const noexcept{return x+width;}
    float Bottom() const noexcept{return y+height;}
};
struct MenuReplayOriginalLayout final {
    // Exact local BNW ReplayViewer.xml c10c832c...442f6d. MainPanel and the
    // ornate frame are root siblings; nesting MainPanel in the frame is wrong.
    MenuReplayBounds frame,main,body,messages,text,selector,graphSelector,graphLegend,graph,graphStatus;
    MenuReplayBounds map,slider,playPause,turnCaption,back,messageUp,messageDown,messageTrack;
    float messageWrapWidth=890,messageTopPadding=5,messageBottomPadding=5,messageStackPadding=1;
    float originalBottomSpacer=63;
    float legendRowWidth=150,legendRowHeight=30,legendRowPitch=32;
    float legendNameOffsetX=36,legendNameOffsetY=14;
    static MenuReplayOriginalLayout At(float width=1920,float height=1080){
        if(width<960 || height<700 || width>8192 || height>8192)
            throw std::invalid_argument("Original replay layout requires a bounded logical viewport");
        MenuReplayOriginalLayout out;
        out.frame={(width-960)/2,(height-628)/2+36,960,628};
        out.main={(width-920)/2,(height-440)/2,920,440};
        const auto x=out.main.x,y=out.main.y;
        out.body={x,y+35,920,405};out.messages=out.body;out.text={x+10,y+35,890,405};
        out.selector={x+660,y,260,27};out.graphSelector={x,y,400,27};
        out.graphLegend={x,y+35,160,380};out.graph={x+160,y+55,720,360};
        out.graphStatus={x+160,y+415,720,25};out.map={x,y+35,920,360};
        out.slider={x+210,y+408,500,32};out.playPause={x+760,y+408,150,32};
        out.turnCaption={x+10,y+410,190,20};
        const auto footerX=out.frame.x+(960-910)/2.0f,footerY=out.frame.Bottom()-42-53;
        out.back={footerX+14,footerY+(53-32)/2.0f,150,32};
        out.messageUp={x+902,y+35,18,18};out.messageDown={x+902,y+420,18,18};
        out.messageTrack={x+902,y+53,18,369};return out;
    }
};
}
