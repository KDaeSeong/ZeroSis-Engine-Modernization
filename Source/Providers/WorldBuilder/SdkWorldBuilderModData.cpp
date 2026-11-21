#include "SdkWorldBuilderModData.h"
#include <memory>
#include <utility>

namespace {
template<class T> class PreparedArray {
public:
    T* data;uint size,constructed;
    explicit PreparedArray(size_t count):data(NULL),size(0),constructed(0){
        if(count>UINT_MAX/sizeof(T))throw std::length_error("WorldBuilder array exceeds SDK width");
        size=static_cast<uint>(count);
        if(size){data=static_cast<T*>(FireMallocAlignedNoTracking(size_t(size)*sizeof(T),__alignof(T),__FILE__,__LINE__));if(!data)throw std::bad_alloc();}
        try{for(;constructed<size;++constructed)new(data+constructed)T();}catch(...){Clear();throw;}
    }
    PreparedArray(PreparedArray&& other) noexcept:data(other.data),size(other.size),constructed(other.constructed){other.data=NULL;other.size=other.constructed=0;}
    ~PreparedArray(){Clear();}
    T* Release() noexcept {T* p=data;data=NULL;size=constructed=0;return p;}
private:
    PreparedArray(const PreparedArray&);PreparedArray& operator=(const PreparedArray&);
    void Clear() noexcept {for(uint i=0;i<constructed;++i)data[i].~T();FireFreeAlignedNoTracking(data);data=NULL;size=constructed=0;}
};
struct PreparedStrings {
    std::unique_ptr<char[]> data;uint size;
    explicit PreparedStrings(const std::vector<char>& bytes):size(0){if(bytes.size()>UINT_MAX)throw std::length_error("WorldBuilder string buffer too large");
        size=static_cast<uint>(bytes.size());if(size){data.reset(new char[size]);std::memcpy(data.get(),bytes.data(),size);}}
};
uint Append(std::vector<char>& strings,const char* value){
    if(!value)value="";const size_t length=std::strlen(value);
    if(strings.size()>UINT_MAX || length>=UINT_MAX-strings.size())throw std::length_error("WorldBuilder string buffer overflow");
    const uint id=static_cast<uint>(strings.size());strings.insert(strings.end(),value,value+length+1);return id;
}
template<class T> dword Bits(T value){static_assert(sizeof(T)==sizeof(dword),"SDK field width");dword bits;std::memcpy(&bits,&value,4);return bits;}
template<class T> T Value(dword bits){static_assert(sizeof(T)==sizeof(dword),"SDK field width");T value;std::memcpy(&value,&bits,4);return value;}
}

// Access declarations only; all original object fields/layouts stay intact.
// Prepared arrays own every allocation until the final non-allocating commit.
struct ZeroSisWorldBuilderModDataAccess {
    template<class T,uint N,bool Pod,uint Pool,uint Tag>
    static void Install(FStaticVector<T,N,Pod,Pool,Tag>& target,PreparedArray<T>& prepared) noexcept {
        target.clear();if(target.m_pData!=reinterpret_cast<T*>(target.m_aData))FireFreeAlignedNoTracking(target.m_pData);
        const uint count=prepared.size;target.m_pData=prepared.Release();target.m_uiCurrSize=target.m_uiCurrMaxSize=count;target.m_bIsResized=true;
    }
    static void Install(FFastVector<dword,true>& target,PreparedArray<dword>& prepared) noexcept {
        FireFreeAlignedNoTracking(target.m_pData);const uint count=prepared.size;target.m_pData=prepared.Release();target.m_uiCurrSize=target.m_uiCurrMaxSize=count;
    }
    static void Install(ModDataStringBuffer& target,PreparedStrings& prepared) noexcept {
        delete[] target.m_szBuffer;target.m_szBuffer=prepared.data.release();target.m_uiSize=target.m_uiReservedSize=prepared.size;
    }
    static std::vector<char> Strings(const ModDataStringBuffer& source){return source.m_uiSize?std::vector<char>(source.m_szBuffer,source.m_szBuffer+source.m_uiSize):std::vector<char>();}
    static ZeroSisWorldBuilder::ModSchema Schema(const ModType& source){
        ZeroSisWorldBuilder::ModSchema out;
        for(uint i=0;i<source.m_kFields.size();++i){const ModType::Field& f=source.m_kFields[i];ZeroSisWorldBuilder::ModField value={f.dwFieldType,f.dwFieldName,f.dwDefault};out.fields.push_back(value);}
        for(uint i=0;i<source.m_kEnums.size();++i){const ModEnum& e=source.m_kEnums[i];std::vector<std::uint32_t> members;
            for(uint j=0;j<e.m_kMembers.size();++j)members.push_back(e.m_kMembers[j]);out.enums.push_back(std::move(members));}
        return out;
    }
    static ZeroSisWorldBuilder::ModDocument Snapshot(const CvWorldBuilderMapModData& source){
        ZeroSisWorldBuilder::ModDocument out;out.map=Schema(source.m_kMapModData);out.plot=Schema(source.m_kPlotModData);out.strings=Strings(source.m_kStringBuffer);
        for(uint i=0;i<source.m_kData.size();++i)out.values.push_back(source.m_kData[i]);return out;
    }
    static PreparedArray<ModType::Field> Fields(const ZeroSisWorldBuilder::ModSchema& schema){
        PreparedArray<ModType::Field> out(schema.fields.size());for(uint i=0;i<out.size;++i){out.data[i].dwFieldType=schema.fields[i].type;out.data[i].dwFieldName=schema.fields[i].name;out.data[i].dwDefault=schema.fields[i].value;}return out;
    }
    static PreparedArray<uint> Members(const std::vector<std::uint32_t>& values){PreparedArray<uint> out(values.size());for(uint i=0;i<out.size;++i)out.data[i]=values[i];return out;}
    static PreparedArray<ModEnum> Enums(const ZeroSisWorldBuilder::ModSchema& schema,ModDataStringBuffer& strings){
        PreparedArray<ModEnum> out(schema.enums.size());for(uint i=0;i<out.size;++i){PreparedArray<uint> members=Members(schema.enums[i]);
            out.data[i].m_pkStringBuffer=&strings;Install(out.data[i].m_kMembers,members);}return out;
    }
    static PreparedArray<dword> Values(const std::vector<std::uint32_t>& values){PreparedArray<dword> out(values.size());for(uint i=0;i<out.size;++i)out.data[i]=values[i];return out;}
    static void Commit(CvWorldBuilderMapModData& target,const ZeroSisWorldBuilder::ModDocument& document){
        ZeroSisWorldBuilder::ValidateModDocument(document);
        PreparedStrings strings(document.strings);PreparedArray<ModType::Field> mapFields=Fields(document.map),plotFields=Fields(document.plot);
        PreparedArray<ModEnum> mapEnums=Enums(document.map,target.m_kStringBuffer),plotEnums=Enums(document.plot,target.m_kStringBuffer);
        PreparedArray<dword> values=Values(document.values);
        Install(target.m_kMapModData.m_kFields,mapFields);Install(target.m_kMapModData.m_kEnums,mapEnums);
        Install(target.m_kPlotModData.m_kFields,plotFields);Install(target.m_kPlotModData.m_kEnums,plotEnums);
        Install(target.m_kData,values);Install(target.m_kStringBuffer,strings);
    }
    static void AddField(ModType& target,const char* name,dword type,dword value,const char* text){
        ZeroSisWorldBuilder::ModSchema schema=Schema(target);std::vector<char> bytes=Strings(target.m_kStringBuffer);
        const uint nameId=Append(bytes,name);if(type==ModType::TYPE_STRING)value=Append(bytes,text);
        ZeroSisWorldBuilder::ModField field={type,nameId,value};schema.fields.push_back(field);
        PreparedStrings strings(bytes);PreparedArray<ModType::Field> fields=Fields(schema);
        Install(target.m_kFields,fields);Install(target.m_kStringBuffer,strings);
    }
    static ModEnum& AddEnum(ModType& target,const char* name,int value){
        ZeroSisWorldBuilder::ModSchema schema=Schema(target);std::vector<char> bytes=Strings(target.m_kStringBuffer);
        if(schema.enums.size()>UINT_MAX-3u)throw std::length_error("Too many WorldBuilder enums");
        const uint index=static_cast<uint>(schema.enums.size());const uint nameId=Append(bytes,name);
        ZeroSisWorldBuilder::ModField field={3u+index,nameId,Bits(value)};schema.fields.push_back(field);schema.enums.push_back(std::vector<std::uint32_t>());
        PreparedStrings strings(bytes);PreparedArray<ModType::Field> fields=Fields(schema);PreparedArray<ModEnum> enums=Enums(schema,target.m_kStringBuffer);
        Install(target.m_kFields,fields);Install(target.m_kEnums,enums);Install(target.m_kStringBuffer,strings);return target.m_kEnums[index];
    }
    static void AddMember(ModEnum& target,const char* value){
        if(!target.m_pkStringBuffer)throw std::logic_error("Unbound WorldBuilder enum");
        std::vector<char> bytes=Strings(*target.m_pkStringBuffer);std::vector<std::uint32_t> values;
        for(uint i=0;i<target.m_kMembers.size();++i)values.push_back(target.m_kMembers[i]);values.push_back(Append(bytes,value));
        PreparedStrings strings(bytes);PreparedArray<uint> members=Members(values);Install(target.m_kMembers,members);Install(*target.m_pkStringBuffer,strings);
    }
    static void CopyEnum(ModEnum& target,const ModEnum& source){std::vector<std::uint32_t> values;
        for(uint i=0;i<source.m_kMembers.size();++i)values.push_back(source.m_kMembers[i]);PreparedArray<uint> members=Members(values);
        Install(target.m_kMembers,members);target.m_pkStringBuffer=source.m_pkStringBuffer;
    }
    static void CopyType(ModType& target,const ModType& source){const ZeroSisWorldBuilder::ModSchema schema=Schema(source);
        PreparedArray<ModType::Field> fields=Fields(schema);PreparedArray<ModEnum> enums=Enums(schema,target.m_kStringBuffer);Install(target.m_kFields,fields);Install(target.m_kEnums,enums);
    }
};

ModDataStringBuffer::ModDataStringBuffer():m_uiSize(0),m_uiReservedSize(0),m_szBuffer(NULL){}
ModDataStringBuffer::~ModDataStringBuffer(){delete[] m_szBuffer;}
void ModDataStringBuffer::Clear(){delete[] m_szBuffer;m_szBuffer=NULL;m_uiSize=m_uiReservedSize=0;}
uint ModDataStringBuffer::AddString(const char* text){std::vector<char> bytes=ZeroSisWorldBuilderModDataAccess::Strings(*this);const uint id=Append(bytes,text);
    PreparedStrings prepared(bytes);ZeroSisWorldBuilderModDataAccess::Install(*this,prepared);return id;}
const char* ModDataStringBuffer::GetString(uint id)const{return id<m_uiSize?m_szBuffer+id:"";}

ModEnum::ModEnum():m_pkStringBuffer(NULL){}
ModEnum::ModEnum(ModDataStringBuffer& strings):m_pkStringBuffer(&strings){}
ModEnum::ModEnum(const ModEnum& other):m_pkStringBuffer(NULL){ZeroSisWorldBuilderModDataAccess::CopyEnum(*this,other);}
void ModEnum::AddMember(const char* text){ZeroSisWorldBuilderModDataAccess::AddMember(*this,text);}
uint ModEnum::GetMemberCount()const{return m_kMembers.size();}
const char* ModEnum::GetMember(uint index)const{return m_pkStringBuffer && index<m_kMembers.size()?m_pkStringBuffer->GetString(m_kMembers[index]):NULL;}

ModType::ModType(ModDataStringBuffer& strings):m_kStringBuffer(strings){}
ModType::ModType(const ModType& other):m_kStringBuffer(other.m_kStringBuffer){ZeroSisWorldBuilderModDataAccess::CopyType(*this,other);}
void ModType::Clear(){m_kFields.clear();m_kEnums.clear();}
void ModType::AddField(const char* name,bool value){ZeroSisWorldBuilderModDataAccess::AddField(*this,name,TYPE_BOOL,value?1u:0u,NULL);}
void ModType::AddField(const char* name,float value){ZeroSisWorldBuilderModDataAccess::AddField(*this,name,TYPE_FLOAT,Bits(value),NULL);}
void ModType::AddField(const char* name,const char* value){ZeroSisWorldBuilderModDataAccess::AddField(*this,name,TYPE_STRING,0,value);}
ModEnum& ModType::AddEnumField(const char* name,int value){return ZeroSisWorldBuilderModDataAccess::AddEnum(*this,name,value);}
uint ModType::GetFieldCount()const{return m_kFields.size();}
const char* ModType::GetFieldName(uint i)const{return i<m_kFields.size()?m_kStringBuffer.GetString(m_kFields[i].dwFieldName):NULL;}
ModType::FieldType ModType::GetFieldType(uint i)const{return i>=m_kFields.size()?TYPE_INVALID:m_kFields[i].dwFieldType>=TYPE_ENUM?TYPE_ENUM:static_cast<FieldType>(m_kFields[i].dwFieldType);}
bool ModType::GetFieldDefaultAsBool(uint i)const{return i<m_kFields.size() && m_kFields[i].dwDefault!=0;}
int ModType::GetFieldDefaultAsInt(uint i)const{return i<m_kFields.size()?Value<int>(m_kFields[i].dwDefault):0;}
float ModType::GetFieldDefaultAsFloat(uint i)const{return i<m_kFields.size()?Value<float>(m_kFields[i].dwDefault):0.0f;}
const char* ModType::GetFieldDefaultAsString(uint i)const{return i<m_kFields.size()?m_kStringBuffer.GetString(m_kFields[i].dwDefault):"";}
const ModEnum* ModType::GetFieldEnumType(uint i)const{if(i>=m_kFields.size() || m_kFields[i].dwFieldType<TYPE_ENUM)return NULL;
    const dword index=m_kFields[i].dwFieldType-TYPE_ENUM;return index<m_kEnums.size()?&m_kEnums[index]:NULL;}

ModDataEntry::ModDataEntry(ModType& type,dword* fields):m_kModType(type),m_aFields(fields){}
void ModDataEntry::SetField(uint i,bool value){if(!m_aFields || i>=m_kModType.GetFieldCount())throw std::out_of_range("Invalid map mod-data field");m_aFields[i]=value?1u:0u;}
void ModDataEntry::SetField(uint i,int value){if(!m_aFields || i>=m_kModType.GetFieldCount())throw std::out_of_range("Invalid map mod-data field");m_aFields[i]=Bits(value);}
void ModDataEntry::SetField(uint i,float value){if(!m_aFields || i>=m_kModType.GetFieldCount())throw std::out_of_range("Invalid map mod-data field");m_aFields[i]=Bits(value);}
void ModDataEntry::SetField(uint i,const char* value){if(!m_aFields || i>=m_kModType.GetFieldCount())throw std::out_of_range("Invalid map mod-data field");const uint id=m_kModType.m_kStringBuffer.AddString(value);m_aFields[i]=id;}
void ModDataEntry::SetFieldToDefault(uint i){if(!m_aFields || i>=m_kModType.GetFieldCount())throw std::out_of_range("Invalid map mod-data field");m_aFields[i]=m_kModType.m_kFields[i].dwDefault;}
bool ModDataEntry::GetFieldAsBool(uint i)const{return m_aFields && i<m_kModType.GetFieldCount() && m_aFields[i]!=0;}
int ModDataEntry::GetFieldAsInt(uint i)const{return m_aFields && i<m_kModType.GetFieldCount()?Value<int>(m_aFields[i]):0;}
float ModDataEntry::GetFieldAsFloat(uint i)const{return m_aFields && i<m_kModType.GetFieldCount()?Value<float>(m_aFields[i]):0.0f;}
const char* ModDataEntry::GetFieldAsString(uint i)const{return m_aFields && i<m_kModType.GetFieldCount()?m_kModType.m_kStringBuffer.GetString(m_aFields[i]):"";}
bool ModDataEntry::IsFieldDefaultValue(uint i)const{return m_aFields && i<m_kModType.GetFieldCount() && m_aFields[i]==m_kModType.m_kFields[i].dwDefault;}

CvWorldBuilderMapModData::CvWorldBuilderMapModData():m_kMapModData(m_kStringBuffer),m_kPlotModData(m_kStringBuffer){}
void CvWorldBuilderMapModData::InitDataEntries(uint plots){
    const size_t globals=m_kMapModData.GetFieldCount(),perPlot=m_kPlotModData.GetFieldCount();
    if(globals>UINT_MAX/sizeof(dword) || (perPlot && plots>(UINT_MAX/sizeof(dword)-globals)/perPlot))throw std::length_error("Map mod-data plot count overflow");
    const size_t count=globals+size_t(plots)*perPlot;PreparedArray<dword> values(count);
    for(uint i=0;i<values.size;++i){if(i<m_kData.size())values.data[i]=m_kData[i];
        else values.data[i]=i<globals?m_kMapModData.m_kFields[i].dwDefault:m_kPlotModData.m_kFields[static_cast<uint>((i-globals)%perPlot)].dwDefault;}
    ZeroSisWorldBuilderModDataAccess::Install(m_kData,values);
}
void CvWorldBuilderMapModData::ResetTypes(){m_kData.clear();m_kMapModData.Clear();m_kPlotModData.Clear();m_kStringBuffer.Clear();}
ModDataEntry CvWorldBuilderMapModData::GetMapDataEntry(){if(m_kData.size()<m_kMapModData.GetFieldCount())throw std::out_of_range("Map mod-data not initialized");return ModDataEntry(m_kMapModData,m_kData.empty()?NULL:m_kData.begin());}
ModDataEntry CvWorldBuilderMapModData::GetPlotDataEntry(uint plot){
    const size_t count=m_kPlotModData.GetFieldCount(),globals=m_kMapModData.GetFieldCount();
    if(count && plot>(std::numeric_limits<size_t>::max()-globals)/count)throw std::out_of_range("Mod-data plot index overflow");
    const size_t start=globals+size_t(plot)*count;
    if(start>m_kData.size() || count>m_kData.size()-start)throw std::out_of_range("Invalid mod-data plot");
    return ModDataEntry(m_kPlotModData,count?m_kData.begin()+start:NULL);
}
size_t CvWorldBuilderMapModData::GetSerializedSize()const{return ZeroSisWorldBuilder::WriteModDocument(ZeroSisWorldBuilderModDataAccess::Snapshot(*this)).size();}
void CvWorldBuilderMapModData::Serialize(void* output)const{if(!output)throw std::invalid_argument("Null mod-data output");
    const std::vector<unsigned char> bytes=ZeroSisWorldBuilder::WriteModDocument(ZeroSisWorldBuilderModDataAccess::Snapshot(*this));std::memmove(output,bytes.data(),bytes.size());}
void CvWorldBuilderMapModData::Deserialize(const void* input){
    // Public SDK compatibility entry. It has no byte count: only trusted data
    // may reach it. File readers must call the checked boundary below.
    const ZeroSisWorldBuilder::ModDocument document=ZeroSisWorldBuilder::ReadModDocument(input,std::numeric_limits<size_t>::max(),false);
    ZeroSisWorldBuilderModDataAccess::Commit(*this,document);
}
namespace ZeroSisWorldBuilder {
void DeserializeModData(CvWorldBuilderMapModData& target,const void* bytes,size_t length){const ModDocument document=ReadModDocument(bytes,length);ZeroSisWorldBuilderModDataAccess::Commit(target,document);}
}
