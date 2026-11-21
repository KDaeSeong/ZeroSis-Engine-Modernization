#include "SdkWorldBuilderMapBridge.h"
#include <FireWorks/FIFile.h>
#include <memory>
namespace {
struct CloseFile {void operator()(FIFile* f)const noexcept{if(!f)return;try{if(f->IsOpen())f->Close();}catch(...){}delete f;}};
typedef std::unique_ptr<FIFile,CloseFile> File;
void ReadExactly(FIFile& file,void* buffer,uint length){byte* p=static_cast<byte*>(buffer);uint at=0;
    while(at<length){const uint read=file.Read(p+at,length-at);if(!read || read>length-at)throw std::runtime_error("Short map read");at+=read;}}
}
bool CvWorldBuilderMap::Load(const wchar_t* filename,const CvWorldBuilderMapTypeDesc& types,bool scenario){
    try{if(!filename || !*filename)return false;File file(FIFileSystem::GetInstance().Create(filename,FIFile::modeRead));if(!file || !file->IsOpen())return false;
        ZeroSisWorldBuilder::MapBytes bytes(file->GetLength());if(bytes.empty())return false;ReadExactly(*file,bytes.data(),static_cast<uint>(bytes.size()));if(file->Close()!=FILE_OK)return false;
        ZeroSisWorldBuilder::LoadMapBytes(*this,bytes.data(),bytes.size(),types,scenario);return true;
    }catch(...){return false;}
}
bool CvWorldBuilderMap::Save(const wchar_t* filename,const CvWorldBuilderMapTypeDesc& types,bool scenario)const{
    try{if(!filename || !*filename)return false;const auto bytes=ZeroSisWorldBuilder::SaveMapBytes(*this,types,scenario);
        // FIFile's length/position contract is uint even in the x64 SDK.
        // Reject an unrepresentable file before opening its destination.
        if(bytes.size()>UINT_MAX)return false;
        // Serialization and validation finish before opening/truncating output.
        // FIFile has no atomic replace API; a write/close failure is reported and
        // may leave a partial destination. The real filesystem host must supply
        // transactional staging for release-quality file replacement.
        File file(FIFileSystem::GetInstance().Create(filename,FIFile::modeWrite));if(!file || !file->IsOpen())return false;
        size_t at=0;while(at<bytes.size()){const uint left=static_cast<uint>(bytes.size()-at);const uint written=file->Write(bytes.data()+at,left);if(!written || written>left)return false;at+=written;}
        return file->Close()==FILE_OK;
    }catch(...){return false;}
}
uint CvWorldBuilderMap::PreviewPlayableCivCount(const wchar_t* filename){
    try{if(!filename || !*filename)return 0;File file(FIFileSystem::GetInstance().Create(filename,FIFile::modeRead));if(!file || !file->IsOpen() || file->GetLength()<10)return 0;
        byte header[10];ReadExactly(*file,header,10);if(file->Close()!=FILE_OK)return 0;const unsigned version=header[0]&127;
        if(version!=6 && version!=7 && version!=9 && version!=10 && version!=11 && version!=12)return 0;
        uint width=0,height=0;for(unsigned i=0;i<4;++i){width|=uint(header[1+i])<<(i*8);height|=uint(header[5+i])<<(i*8);}
        if(width>MaxMapSize || height>MaxMapSize || (height && width>MaxMapSize/height) || header[9]>MaxPlayers)return 0;return header[9];
    }catch(...){return 0;}
}
