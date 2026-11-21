#include "SdkDatabaseIncludes.h"
extern "C" __declspec(dllimport) int ZeroSisDatabaseFaultInitialize();
extern "C" __declspec(dllimport) void ZeroSisDatabaseFaultArm(long long);
extern "C" __declspec(dllimport) unsigned long ZeroSisDatabaseFaultDisarm();
extern "C" __declspec(dllimport) bool ZeroSisDatabaseFaultTriggered();
extern "C" __declspec(dllimport) int ZeroSisDatabaseFaultKind();
static unsigned long checks=0,failures=0,recoveries=0,successes=0,cppFaults=0,sqlFaults=0;
static void require(bool value) { ++checks;if(!value) { fprintf(stderr,"CHECK|%lu\n",checks);throw std::runtime_error("database assignment check"); } }
static void allocationFailures(bool sameOwner,bool emptySource) {
    bool exhausted=false;
    for(unsigned index=0;index<256;++index) {
        Database::Connection a(":memory:",6),b(":memory:",6);Database::Results source("Value"),destination("Old");
        if(!emptySource) { require(a.Execute(source,"SELECT ?1 AS Value UNION ALL SELECT ?2"));require(source.Bind(1,5));require(source.Bind(2,9));require(source.Step());require(source.ColumnPosition("Value")==0); }
        Database::Connection& oldOwner=sameOwner?a:b;require(oldOwner.Execute(destination,"SELECT 99 AS Old"));require(destination.Step());require(destination.ColumnPosition("Old")==0);
        const int beforeA=a.StatementCount(),beforeB=b.StatementCount();
        bool threw=false;ZeroSisDatabaseFaultArm(index);
        try { destination=source; }catch(const std::exception&) { threw=true; }
        const unsigned long allocations=ZeroSisDatabaseFaultDisarm();const bool injected=ZeroSisDatabaseFaultTriggered();
        if(injected) { const int kind=ZeroSisDatabaseFaultKind();if(kind==1)++cppFaults;else if(kind==2)++sqlFaults;else require(false); }
        if(threw) {
            ++failures;require(injected);require(destination.GetInt(0)==99);require(!strcmp(destination.GetColumns(),"Old"));require(destination.ColumnPosition("Old")==0);
            require(a.StatementCount()==beforeA);require(b.StatementCount()==beforeB);
        }else {
            ++successes;if(injected)++recoveries;require(!strcmp(destination.GetColumns(),"Value"));
            if(emptySource)require(destination.ColumnCount()==0);
            else { require(destination.Step());require(destination.GetText(0)==NULL);require(destination.ColumnPosition("Value")==0); }
            if(!emptySource) { require(a.StatementCount()==2);require(b.StatementCount()==0); }
            else { require(a.StatementCount()==0);require(b.StatementCount()==0); }
        }
        if(!emptySource) { require(source.GetInt(0)==5);require(source.Step());require(source.GetInt(0)==9); }
        if(!injected) { require(!threw);require(index==allocations);exhausted=true;break; }
    }
    require(exhausted);
}
static void lifetimeAndSelf() {
    Database::Connection first(":memory:",6),second(":memory:",6);Database::Results source("A"),destination("B");
    require(first.Execute(source,"SELECT 17 AS A UNION ALL SELECT 18"));require(source.Step());require(second.Execute(destination,"SELECT 99 AS B"));require(destination.Step());
    ZeroSisDatabaseFaultArm(0);source=source;const unsigned long used=ZeroSisDatabaseFaultDisarm();require(used==0);require(!ZeroSisDatabaseFaultTriggered());require(source.GetInt(0)==17);
    destination=source;second.Close();require(destination.Step());require(destination.GetInt(0)==17);source.Release();require(destination.Step());require(destination.GetInt(0)==18);
    first.Close();require(!destination.Step());require(destination.ColumnCount()==0);
    Database::Results empty;destination=empty;require(destination.ColumnCount()==0);require(!strcmp(destination.GetColumns(),"*"));
    Database::Connection db(":memory:",6);Database::SingleResult single;require(db.Execute(single,"SELECT 23"));Database::SingleResult assigned;assigned=single;
    require(assigned.SingleQuery());require(assigned.Step());require(assigned.GetInt(0)==23);require(single.GetInt(0)==23);
    assigned.Release();single.Release();
    // A schema change can make copied SQL invalid while another destination remains usable.
    require(db.Execute("CREATE TABLE T(ID INT)"));Database::Results table;require(db.Execute(table,"SELECT ID FROM T"));table.Reset();require(db.Execute("DROP TABLE T"));
    require(db.Execute(destination,"SELECT 55 AS Stable"));require(destination.Step());bool failed=false;
    try { destination=table; }catch(const std::runtime_error&) { failed=true; }
    require(failed);require(destination.GetInt(0)==55);
}
int main() {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);setvbuf(stdout,NULL,_IONBF,0);
    try {
        require(ZeroSisDatabaseFaultInitialize()==0);lifetimeAndSelf();
        allocationFailures(true,false);allocationFailures(false,false);allocationFailures(true,true);allocationFailures(false,true);
        require(cppFaults>0&&sqlFaults>0);
        printf("ASSIGNMENT|failures=%lu|recoveries=%lu|successes=%lu|cpp_faults=%lu|sqlite_faults=%lu|same_and_different_owner|empty_and_prepared\n",failures,recoveries,successes,cppFaults,sqlFaults);
        printf("PASS|%lu\n",checks);return 0;
    }catch(const std::exception& e) { ZeroSisDatabaseFaultDisarm();fprintf(stderr,"FAILED|%lu|%s\n",checks,e.what());return 1; }
}
