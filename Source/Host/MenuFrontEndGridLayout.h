#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>
#include <vector>

namespace ZeroSisHost {
// Retains every authored nine-grid cap independently. A corner and its
// adjacent edge need not have equal height or width in the original styles.
// Pieces expose column, row and source[4], as the existing asset reader does.
template<class Pieces>
std::vector<std::array<float,4>> BuildMenuFrontEndGridLayout(unsigned kind,const Pieces& pieces,
    float x,float y,float width,float height){
    const auto valid=[](float a,float b,float w,float h){
        return std::isfinite(a) && std::isfinite(b) && std::isfinite(w) && std::isfinite(h) &&
            std::fabs(a)<100000 && std::fabs(b)<100000 && w>0 && h>0 && w<100000 && h<100000;
    };
    if(kind>3 || pieces.empty() || pieces.size()>9 || !valid(x,y,width,height))
        throw std::runtime_error("Invalid original grid layout request");
    float sizes[9][2]{};bool present[9]{};
    float left=0,right=0,top=0,bottom=0;
    for(const auto& piece:pieces){
        const auto w=piece.source[2]-piece.source[0],h=piece.source[3]-piece.source[1];
        if(piece.column>2 || piece.row>2 || !valid(piece.source[0],piece.source[1],w,h))
            throw std::runtime_error("Invalid original grid cap");
        const auto index=piece.row*3+piece.column;
        if(present[index])throw std::runtime_error("Duplicate original grid cap");
        present[index]=true;sizes[index][0]=w;sizes[index][1]=h;
        if(piece.column==0)left=(std::max)(left,w);if(piece.column==2)right=(std::max)(right,w);
        if(piece.row==0)top=(std::max)(top,h);if(piece.row==2)bottom=(std::max)(bottom,h);
    }
    std::array<float,4> targets[9]{};
    if(kind==0){
        const float outerRight=x+width,outerBottom=y+height;
        const auto assign=[&](unsigned index,float l,float t,float r,float b){
            if(r<l || b<t)throw std::runtime_error("Original grid is smaller than its authored caps");
            targets[index]={{l,t,r,b}};
        };
        assign(0,x,y,x+sizes[0][0],y+sizes[0][1]);
        assign(1,x+sizes[0][0],y,outerRight-sizes[2][0],y+sizes[1][1]);
        assign(2,outerRight-sizes[2][0],y,outerRight,y+sizes[2][1]);
        assign(3,x,y+sizes[0][1],x+sizes[3][0],outerBottom-sizes[6][1]);
        assign(4,x+sizes[3][0],y+sizes[1][1],outerRight-sizes[5][0],outerBottom-sizes[7][1]);
        assign(5,outerRight-sizes[5][0],y+sizes[2][1],outerRight,outerBottom-sizes[8][1]);
        assign(6,x,outerBottom-sizes[6][1],x+sizes[6][0],outerBottom);
        assign(7,x+sizes[6][0],outerBottom-sizes[7][1],outerRight-sizes[8][0],outerBottom);
        assign(8,outerRight-sizes[8][0],outerBottom-sizes[8][1],outerRight,outerBottom);
    }else{
        // Preserve the existing three-slice and full-stretch policies exactly.
        if(kind==1){top=bottom=0;}if(kind==2){left=right=0;}
        if(kind==3){left=right=top=bottom=0;}
        if(width<left+right || height<top+bottom)
            throw std::runtime_error("Original grid is smaller than its source caps");
        const float xs[]={x,x+left,x+width-right,x+width},ys[]={y,y+top,y+height-bottom,y+height};
        for(const auto& piece:pieces){
            const auto column=kind==2 || kind==3?1:piece.column,row=kind==1 || kind==3?1:piece.row;
            targets[piece.row*3+piece.column]={{xs[column],ys[row],xs[column+1],ys[row+1]}};
        }
    }
    std::vector<std::array<float,4>> result;result.reserve(pieces.size());
    for(const auto& piece:pieces)result.push_back(targets[piece.row*3+piece.column]);
    return result;
}
}
