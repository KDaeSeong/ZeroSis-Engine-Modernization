#pragma once
#include "SdkHostIncludes.h"
#include <ICvDLLScriptSystem.h>
#include <cmath>
#include <vector>

namespace ZeroSisHost {
struct ScriptValue {
    ICvEngineScriptSystemArgs1::ArgType type=ICvEngineScriptSystemArgs1::ARGTYPE_NULL;
    bool boolean=false;int integer=0;float number=0;std::string text;
};
class ScriptArguments final : public ICvEngineScriptSystemArgs1 {
public:
    explicit ScriptArguments(unsigned reserve):owner_(GetCurrentThreadId()){values_.reserve(reserve);}
    unsigned Push(bool value) override{ScriptValue item;item.type=ARGTYPE_BOOL;item.boolean=value;return Add(std::move(item));}
    unsigned Push(int value) override{ScriptValue item;item.type=ARGTYPE_INT;item.integer=value;return Add(std::move(item));}
    unsigned Push(float value) override{
        if(!std::isfinite(value))throw std::invalid_argument("Non-finite script argument");
        ScriptValue item;item.type=ARGTYPE_FLOAT;item.number=value;return Add(std::move(item));
    }
    unsigned Push(const char* value,std::size_t length) override{
        if(!value && length)throw std::invalid_argument("Null script string with nonzero length");
        ScriptValue item;item.type=ARGTYPE_STRING;if(length)item.text.assign(value,length);return Add(std::move(item));
    }
    unsigned PushNULL() override{return Add(ScriptValue());}
    unsigned Count() override{Owner();return static_cast<unsigned>(values_.size());}
    ArgType GetType(unsigned index) override{Owner();return index<values_.size()?values_[index].type:ARGTYPE_NONE;}
    bool GetBool(unsigned index,bool& value) override{if(GetType(index)!=ARGTYPE_BOOL)return false;value=values_[index].boolean;return true;}
    bool GetInt(unsigned index,int& value) override{if(GetType(index)!=ARGTYPE_INT)return false;value=values_[index].integer;return true;}
    bool GetFloat(unsigned index,float& value) override{if(GetType(index)!=ARGTYPE_FLOAT)return false;value=values_[index].number;return true;}
    bool GetString(unsigned index,char*& value) override{
        if(GetType(index)!=ARGTYPE_STRING)return false;value=&values_[index].text[0];return true;
    }
    std::vector<ScriptValue> Snapshot() const{Owner();return values_;}
private:
    void Owner() const{if(owner_!=GetCurrentThreadId())throw std::logic_error("Script arguments require their owner thread");}
    unsigned Add(ScriptValue value){
        Owner();if(values_.size()>=UINT_MAX)throw std::length_error("Too many script arguments");
        const auto index=static_cast<unsigned>(values_.size());values_.push_back(std::move(value));return index;
    }
    const DWORD owner_;
    std::vector<ScriptValue> values_;
};
}
