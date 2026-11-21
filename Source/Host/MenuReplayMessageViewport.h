#pragma once
#include "MenuReplayText.h"
#include <algorithm>
#include <cmath>

namespace ZeroSisHost {
// Index immutable paragraph rows in original vector order. Unlike the legacy
// page index, an offset may begin inside a row and retains the stock63px tail.
class MenuReplayMessageViewport final {
public:
    struct Range final {std::size_t first=0,last=0;};
    explicit MenuReplayMessageViewport(const MenuReplayMessagePages& rows,double bottomPadding=63){
        if(!std::isfinite(bottomPadding) || bottomPadding<0 || bottomPadding>4096)
            throw std::invalid_argument("Replay message bottom padding is invalid");
        starts_.reserve(rows.Rows().size());ends_.reserve(rows.Rows().size());
        double position=0;
        for(const auto& row:rows.Rows()){
            const double height=static_cast<double>(row.before)+row.height+row.after;
            if(!std::isfinite(height) || row.before<0 || row.height<=0 || row.after<0 || height<=0 ||
               !std::isfinite(position+height) || position+height<=position)
                throw std::invalid_argument("Replay message row extent is invalid");
            starts_.push_back(position);position+=height;ends_.push_back(position);
        }
        contentHeight_=position+bottomPadding;
        if(!std::isfinite(contentHeight_) || (bottomPadding>0 && contentHeight_<=position))
            throw std::invalid_argument("Replay message content extent is not representable");
    }
    double ContentHeight() const noexcept{return contentHeight_;}
    std::size_t RowCount() const noexcept{return starts_.size();}
    double RowTop(std::size_t index) const{return starts_.at(index);}
    double RowEnd(std::size_t index) const{return ends_.at(index);}
    double Maximum(double viewportHeight) const {
        ValidateHeight(viewportHeight);
        if(contentHeight_<=viewportHeight)return 0;
        const auto maximum=contentHeight_-viewportHeight;
        if(maximum>=contentHeight_)throw std::invalid_argument("Replay message viewport difference is not representable");
        return maximum;
    }
    double Clamp(double offset,double viewportHeight) const {
        if(!std::isfinite(offset))throw std::invalid_argument("Replay message scroll offset is not finite");
        return (std::max)(0.0,(std::min)(Maximum(viewportHeight),offset));
    }
    Range Visible(double offset,double viewportHeight) const {
        const double top=Clamp(offset,viewportHeight),bottom=top+viewportHeight;
        if(!std::isfinite(bottom) || bottom<=top)throw std::invalid_argument("Replay message viewport range is not representable");
        Range result;
        result.first=static_cast<std::size_t>(std::upper_bound(ends_.begin(),ends_.end(),top)-ends_.begin());
        result.last=static_cast<std::size_t>(std::lower_bound(starts_.begin(),starts_.end(),bottom)-starts_.begin());
        return result;
    }
private:
    static void ValidateHeight(double height){
        if(!std::isfinite(height) || height<=0 || height>32768)
            throw std::invalid_argument("Replay message viewport height is invalid");
    }
    std::vector<double> starts_,ends_;double contentHeight_=0;
};
}
