#include "menu_frontend_scene_fixture.h"
static unsigned checks=0;
static void Check(bool value,const char* label){++checks;if(!value)throw std::runtime_error(label);}
static void Word(std::vector<unsigned char>& bytes,std::size_t offset,std::uint32_t value){std::memcpy(bytes.data()+offset,&value,4);}
static void ExpectBad(const std::vector<unsigned char>& bytes,std::size_t textures=25){
    try{MenuFrontEndAssets value;value.ReadBank(bytes,textures);}catch(const std::exception&){Check(true,"rejection");return;}Check(false,"Malformed bank accepted");
}
static std::set<std::uint64_t> Hits(const Scene& scene){std::set<std::uint64_t> result;for(const auto& hit:scene.hits)result.insert(hit.controlKey);return result;}
static void WriteScene(const Scene& scene,const std::wstring& path){
    std::ofstream file(path,std::ios::binary);if(!file)throw std::runtime_error("Cannot write owned scene proof");
    auto word=[&](std::uint32_t n){file.write(reinterpret_cast<const char*>(&n),4);};
    file.write("ZSUPIX02",8);word(scene.width);word(scene.height);word(static_cast<std::uint32_t>(scene.textures.size()));word(static_cast<std::uint32_t>(scene.sprites.size()));word(static_cast<std::uint32_t>(scene.hits.size()));word(0);
    for(const auto& texture:scene.textures){const auto text=Narrow(texture.path);word(static_cast<std::uint32_t>(text.size()));file.write(text.data(),static_cast<std::streamsize>(text.size()));}
    for(const auto& sprite:scene.sprites){word(sprite.textureIndex);file.write(reinterpret_cast<const char*>(&sprite.controlKey),8);file.write(reinterpret_cast<const char*>(sprite.sourceRect),64);}
    for(const auto& hit:scene.hits){file.write(reinterpret_cast<const char*>(&hit.controlKey),8);file.write(reinterpret_cast<const char*>(hit.bounds),16);}
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc!=4)throw std::runtime_error("Expected asset directory, labels and owned proof packet");
        const auto assets=MenuFrontEndAssets::Load(argv[1]);const auto bytes=Read(std::wstring(argv[1])+L"\\frontend.bin");
        std::map<std::string,std::wstring> labels;const auto labelBytes=Read(argv[2]);std::size_t cursor=0;const auto labelCount=U32(labelBytes,cursor);
        for(std::uint32_t n=0;n<labelCount;++n){const auto ksize=U32(labelBytes,cursor);const std::string key(reinterpret_cast<const char*>(labelBytes.data()+cursor),ksize);cursor+=ksize;
            const auto size=U32(labelBytes,cursor);const std::string text(reinterpret_cast<const char*>(labelBytes.data()+cursor),size);cursor+=size;labels.emplace(key,Widen(text));}
        auto label=[&](const std::string& key){return labels.at(key);};
        const std::wstring current=L"\ud604\uc7ac \uc124\uc815\uc73c\ub85c \uc0c8 \uac8c\uc784";
        auto main=assets->BuildPage(MenuFrontEndPage::Main,true,1,label,current);
        auto single=assets->BuildPage(MenuFrontEndPage::SinglePlayer,true,0,label,current);
        auto disabled=assets->BuildPage(MenuFrontEndPage::SinglePlayer,false,0,label,current);
        auto confirm=assets->BuildPage(MenuFrontEndPage::ExitConfirm,true,0,label,current);
        Check(assets->Controls().size()==16,"Original control inventory");Check(assets->Fonts().size()==3,"Original font inventory");
        Check(Hits(main)==std::set<std::uint64_t>{1,3},"Unsupported main routes received input");
        Check(Hits(single)==std::set<std::uint64_t>{10,11},"Captured setup start/back routes");
        Check(Hits(disabled)==std::set<std::uint64_t>{11},"Start without current setup received input");
        Check(Hits(confirm)==std::set<std::uint64_t>{20,21},"Exit confirmation routes");
        const auto& first=assets->Find(MenuFrontEndPage::Main,"SinglePlayerButton");
        Check(first.x==800 && first.y==386 && first.width==320 && first.height==45,"Original main anchor/stack geometry");
        const auto& exit=assets->Find(MenuFrontEndPage::Main,"ExitButton");Check(exit.y==723,"Original bottom button anchor");
        const auto& yes=assets->Find(MenuFrontEndPage::ExitConfirm,"Yes");Check(yes.x==760 && yes.y==532 && yes.width==400 && yes.height==42,"Original exit button geometry");
        auto base=assets->Background();const auto before=base.sprites.size();
        assets->Button(base,900,100,100,320,45,L"Test");Check(base.sprites.size()>before+8,"Original dynamic button slices missing");Check(base.hits.size()==1,"Owned dynamic button hit");
        assets->Button(base,901,100,150,320,45,L"Test",false);Check(base.hits.size()==1,"Disabled dynamic button hit");
        auto glyphScene=assets->Background();assets->Text(glyphScene,800,L"A B",0,0,320,45);
        Check(glyphScene.sprites.size()==assets->Background().sprites.size()+4,"Blank glyph painted a spacing border");
        const auto& font=assets->Fonts().at(22);const auto& a=font.glyphs.at('A');const auto& b=font.glyphs.at('B');
        auto positioned=assets->Background();assets->Text(positioned,800,L"AB",20,30,320,45);
        const auto index=assets->Background().sprites.size();
        Check(positioned.sprites[index].targetRect[0]==20+a.a+a.originX-font.border,"GGXML first origin");
        Check(positioned.sprites[index+1].targetRect[0]==20+a.a+a.b+a.c+b.a+b.originX-font.border,"GGXML ABC advance");
        auto wrapped=assets->Background();assets->Text(wrapped,800,L"AAAA",0,0,float(a.a+a.b+a.c)*2,100);
        Check(wrapped.sprites[index+font.layers.size()*2].targetRect[1]-wrapped.sprites[index].targetRect[1]==font.lineAdvance,"GGXML wrapped line advance");
        for(auto page:{main,single,disabled,confirm}){
            for(const auto& sprite:page.sprites){Check(sprite.textureIndex==0xffffffffu || sprite.textureIndex<page.textures.size(),"Sprite escaped bank");
                for(float value:sprite.targetRect)Check(std::isfinite(value),"Nonfinite scene geometry");}
            for(const auto& hit:page.hits)Check(hit.bounds[0]>=0 && hit.bounds[1]>=0 && hit.bounds[2]<=1920 && hit.bounds[3]<=1080,"Hit escaped viewport");
        }
        for(const auto size:{0u,1u,7u,8u,12u,100u,static_cast<unsigned>(bytes.size()-1)})ExpectBad(std::vector<unsigned char>(bytes.begin(),bytes.begin()+size));
        auto bad=bytes;bad.push_back(0);ExpectBad(bad);bad=bytes;Word(bad,8,65);ExpectBad(bad);
        bad=bytes;Word(bad,12,3);ExpectBad(bad);bad=bytes;Word(bad,16,3);ExpectBad(bad);
        bad=bytes;Word(bad,24,0);Word(bad,28,0);ExpectBad(bad);bad=bytes;Word(bad,32,0x7fc00000);ExpectBad(bad);
        bad=bytes;Word(bad,40,0xbf800000);ExpectBad(bad);ExpectBad(bytes,0);ExpectBad(bytes,65);
        auto rejected=[&](const std::function<void()>& operation){try{operation();}catch(const std::exception&){Check(true,"invalid text/scene request rejected");return;}Check(false,"Invalid scene request accepted");};
        rejected([&]{auto scene=assets->Background();assets->Text(scene,0,std::wstring(1,wchar_t(0xd800)),0,0,320,45);});
        rejected([&]{auto scene=assets->Background();assets->Text(scene,0,L"Test",0,0,std::numeric_limits<float>::quiet_NaN(),45);});
        rejected([&]{auto scene=assets->Background();assets->Text(scene,0,L"Test",0,0,320,45,MenuFrontEndTextAlign::Left,19);});
        rejected([&]{assets->Page(static_cast<MenuFrontEndPage>(3));});
        auto notice=assets->Background();assets->Text(notice,0,L"\ud750\ub9b0 \ud56d\ubaa9\uc740 \uc544\uc9c1 \uc81c\uacf5\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.",540,1000,840,35,MenuFrontEndTextAlign::Center,20);
        Check(notice.sprites.size()>assets->Background().sprites.size(),"Current supported-scope notice is absent from the original glyph bank");
        assets->Text(main,0,L"ZeroSis'",40,1000,300,35,MenuFrontEndTextAlign::Left,20);
        assets->Text(main,0,L"CPU proof - original artwork; runtime acceptance pending",420,1035,1080,35,MenuFrontEndTextAlign::Center,20);
        WriteScene(main,argv[3]);
        std::printf("{\"status\":\"PASS_ORIGINAL_FRONTEND_FILE_AND_SCENE_COMPONENT\",\"checks\":%u,\"controls\":16,\"texture_bank\":%zu,\"native_window\":false,\"sdk_loaded\":false}\n",checks,main.textures.size());return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}
}
