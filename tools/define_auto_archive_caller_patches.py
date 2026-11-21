"""Migrate x64 auto-variable ownership/names and make vector mutations failure-safe."""
import json
import re
from collect_baseline import PROJECT,digest

PREFIX='auto_callers_'

def main():
    path=PROJECT/'Source/Porting/sdk_x64_patches.json';plan=json.loads(path.read_text(encoding='utf-8'))
    base=PROJECT/'evidence/sdk_x64/attempts/attempt_013/sdk_x64_patches.json';prior=json.loads(base.read_text(encoding='utf-8'))
    retained=[p for p in plan['patches'] if not p['id'].startswith(PREFIX)]
    if retained!=prior['patches'] or len(retained)!=458:raise RuntimeError('The accepted 458-patch baseline changed')
    baseline_count=len(retained);plan['patches']=retained;working={}
    def current(relative):
        if relative not in working:
            text=(PROJECT/'Source/SDK_BNW_Original'/relative).read_bytes().decode('latin1')
            for patch in retained:
                if patch['file']==relative:
                    if text.count(patch['old'])!=patch['count']:raise RuntimeError('Baseline patch drift')
                    text=text.replace(patch['old'],patch['new'])
            working[relative]=text
        return working[relative]
    def add(relative,name,old,new,reason):
        if current(relative).count(old)!=1:raise RuntimeError('AutoArchive patch match drift: '+name)
        source=PROJECT/'Source/SDK_BNW_Original'/relative
        plan['patches'].append(dict(id=PREFIX+name,file=relative,source_sha256=digest(source),old=old,new=new,count=1,reason=reason))
        working[relative]=working[relative].replace(old,new)
    def body(relative,name,signature,replacement,reason):
        text=current(relative);start=text.index(signature);match=re.search(r'\r\n([ \t]*)\{',text[start:])
        if not match:raise RuntimeError('Function body not found: '+signature)
        indent=match[1];begin=start+match.start();closing='\r\n'+indent+'}';end=text.index(closing,start+match.end())+len(closing)
        add(relative,name,text[start:end],text[start:begin]+'\r\n'+indent+'{\r\n'+replacement.strip('\n').replace('\n','\r\n')+closing,reason)
    folder='FirePlace/include/FireWorks/'
    base_header=folder+'FAutoVariableBase.h'
    add(base_header,'registration_owner', '\t//std::string  m_name;',
        '\tfriend class FAutoArchive;\r\n\ttemplate<class ClassType> friend class FAutoArchiveClassContainer;\r\n'
        '\tFAutoArchive* m_archiveOwner;\r\n\tmutable const std::string* m_registeredName;\r\n\t//std::string  m_name;',
        'Source-only x64 ABI migration: base owns registration and an immutable name pointer; rebuild every consumer. Neither pointer is serialized.')
    container=folder+'FAutoArchiveClassContainer.h'
    add(container,'name_includes','#include "FAutoArchive.h"','#include "FAutoArchive.h"\r\n#include "FAutoVariableBase.h"\r\n#include "CvAutoArchiveSupport.h"',
        'Use complete variable declarations and synchronized immutable name storage.')
    body(container,'name_lookup','\tvirtual const std::string * getVariableName(','''        return var.m_archiveOwner == this ? var.m_registeredName : NULL;''',
        'Names follow the variable, not a shifting registration index; no mutable shared-map read.')
    body(container,'name_registration','\tvirtual void setVariableName(','''        if (var.m_archiveOwner != this) throw std::invalid_argument("Name registration requires the owning archive");
        if (!var.m_registeredName) var.m_registeredName = CvAutoArchive::InternName(name);
        else if (*var.m_registeredName != name) throw std::invalid_argument("AutoVariable name is immutable");''',
        'Intern immutable strings under a mutex; expose no name pointer until allocation succeeds; reject conflicting renames.')
    text=current(container)
    add(container,'remove_mutable_names_api','protected:\r\n\tstd::map<size_t, std::string> & getNames() const;\r\n\r\n','',
        'Retire the unused protected mutable name-map escape hatch; all known SDK call sites use get/setVariableName.')
    text=current(container);start=text.index('// rather than storing a duplicate string');end=text.index('//---------------------------------------------------------------------------------------',start)
    add(container,'remove_index_names',text[start:end],'',
        'Remove the unsynchronized per-class index map; immutable interned strings are shared without index aliasing.')
    scalar=folder+'FAutoVariable.h'
    body(scalar,'scalar_base_cleanup','FAutoVariable<ObjectType, ContainerType>::~FAutoVariable()',
        '    // FAutoVariableBase owns removal, including failed derived construction.',
        'Delegate all successful and failed object lifetime cleanup to the base registration owner.')
    body(scalar,'scalar_name_guard','const std::string & FAutoVariable<ObjectType, ContainerType>::name() const',
        '''    const std::string* result = m_owner.getVariableName(*this);
    if (!result) throw std::logic_error("Detached AutoVariable has no name");
    return *result;''','Reject a missing name rather than dereferencing a null pointer.')
    vector=folder+'FAutoVector.h'
    add(vector,'vector_constructor_count',', m_value(reserveSize)',', m_value(CvChecked::Integer<unsigned int>(reserveSize))',
        'Preserve the SDK initial-size meaning, but reject native sizes outside the uint32 wire domain before allocation.')
    prefix='FAutoVariable<std::vector<ElementType>, ClassContainer>::'
    body(vector,'vector_name_guard','const std::string & '+prefix+'name() const',
        '''    const std::string* result = m_owner.getVariableName(*this);
    if (!result) throw std::logic_error("Detached AutoVector has no name");
    return *result;''','Guard detached vector names; base destruction now unregisters vector specializations too.')
    body(vector,'vector_index_guard',prefix+'operator[](size_t index) const','    return m_value.at(index);',
        'Reject out-of-range reads using native-size bounds before dereferencing storage.')
    body(vector,'vector_assign',prefix+'operator=(const std::vector<ElementType> & rhs)',
        '''    CvChecked::Integer<unsigned int>(rhs.size());
    CvAutoArchive::Assign(m_value, m_commands, m_owner, *this, rhs,
        static_cast<unsigned char>(AutoVectorCommand<ElementType>::CLEAR),
        static_cast<unsigned char>(AutoVectorCommand<ElementType>::PUSH_BACK));
    return *this;''','Prepare values and command history before touch/commit; self-assignment through the vector view is safe.')
    body(vector,'vector_load','void '+prefix+'load(FDataStream & loadFrom)',
        '''    std::vector<ElementType> next;
    loadFrom >> next;
    m_owner.touch(*this); // Preserve successful full-load dirty marking from the SDK clear().
    m_value.swap(next);
    m_commands.clear();''','A truncated or failed vector load preserves old values and commands; successful full load keeps legacy dirty marking.')
    body(vector,'vector_load_delta','void '+prefix+'loadDelta(FDataStream & loadFrom)',
        '''    std::vector<ElementType> next;
    loadFrom >> next;
    m_value.swap(next);''','Prepare a full vector delta before commit; preserve legacy command/dirty state on success.')
    reason='Validate bounds/counts and prepare all throwing work before dirty marking and nonthrowing commit; amortized path for scalar elements.'
    body(vector,'vector_set_at','void '+prefix+'setAt(size_t index, const ElementType & v)',
        '''    if (index >= m_value.size()) throw std::out_of_range("AutoVector set index");
    const unsigned int commandIndex = CvChecked::Integer<unsigned int>(index);
    if (!(v == m_value[index])) {
        const AutoVectorCommand<ElementType> command(AutoVectorCommand<ElementType>::SET, commandIndex, v);
        CvAutoArchive::Mutate(m_value, m_commands, m_owner, *this, command, m_value.size(),
            [index](std::vector<ElementType>& values, const ElementType& value) { values[index] = value; });
    }''',reason)
    body(vector,'vector_insert','void '+prefix+'insert(size_t index, const ElementType & v)',
        '''    if (index > m_value.size()) throw std::out_of_range("AutoVector insert index");
    const unsigned int commandIndex = CvChecked::Integer<unsigned int>(index);
    const size_t nextSize = CvAutoArchive::Additional(m_value, 1);
    CvChecked::Integer<unsigned int>(nextSize);
    const AutoVectorCommand<ElementType> command(AutoVectorCommand<ElementType>::INSERT, commandIndex, v);
    CvAutoArchive::Mutate(m_value, m_commands, m_owner, *this, command, nextSize,
        [index](std::vector<ElementType>& values, const ElementType& value) { values.insert(values.begin() + index, value); });''',reason)
    body(vector,'vector_push_back','void '+prefix+'push_back(const ElementType & v)',
        '''    const size_t nextSize = CvAutoArchive::Additional(m_value, 1);
    CvChecked::Integer<unsigned int>(nextSize);
    const AutoVectorCommand<ElementType> command(AutoVectorCommand<ElementType>::PUSH_BACK, 0, v);
    CvAutoArchive::Mutate(m_value, m_commands, m_owner, *this, command, nextSize,
        [](std::vector<ElementType>& values, const ElementType& value) { values.push_back(value); });''',reason)
    body(vector,'vector_clear','void '+prefix+'clear()',
        '''    const AutoVectorCommand<ElementType> command(AutoVectorCommand<ElementType>::CLEAR, 0, ElementType());
    CvAutoArchive::Mutate(m_value, m_commands, m_owner, *this, command, m_value.size(),
        [](std::vector<ElementType>& values, const ElementType&) { values.clear(); });''',reason)
    body(vector,'vector_erase','void '+prefix+'erase(size_t index)',
        '''    if (index >= m_value.size()) throw std::out_of_range("AutoVector erase index");
    const unsigned int commandIndex = CvChecked::Integer<unsigned int>(index);
    const AutoVectorCommand<ElementType> command(AutoVectorCommand<ElementType>::ERASE, commandIndex, ElementType());
    CvAutoArchive::Mutate(m_value, m_commands, m_owner, *this, command, m_value.size(),
        [index](std::vector<ElementType>& values, const ElementType&) { values.erase(values.begin() + index); });''',reason)
    body(vector,'vector_resize','void '+prefix+'resize(size_t count)',
        '''    const unsigned int commandIndex = CvChecked::Integer<unsigned int>(count);
    const AutoVectorCommand<ElementType> command(AutoVectorCommand<ElementType>::RESIZE, commandIndex, ElementType());
    CvAutoArchive::Mutate(m_value, m_commands, m_owner, *this, command, count,
        [count](std::vector<ElementType>& values, const ElementType&) { values.resize(count); });''',reason)
    body(vector,'vector_resize_value','void '+prefix+'resize(size_t count, const ElementType & v)',
        '''    const unsigned int commandIndex = CvChecked::Integer<unsigned int>(count);
    const AutoVectorCommand<ElementType> command(AutoVectorCommand<ElementType>::RESIZE_WITH_VALUE, commandIndex, v);
    CvAutoArchive::Mutate(m_value, m_commands, m_owner, *this, command, count,
        [count](std::vector<ElementType>& values, const ElementType& value) { values.resize(count, value); });''',reason)
    path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ledger_path=PROJECT/'evidence/numeric_boundaries/edit_ledger.json';ledger=json.loads(ledger_path.read_text(encoding='utf-8'))
    ledger['patch_specification_sha256']=digest(path)
    ledger['supplemental_non_numeric_patches']=[p['id'] for p in plan['patches'] if p['id'].startswith(('serialization_','temp_callers_',PREFIX))]
    ledger['unchanged_auto_archive_caller_baseline']={'path':str(base),'sha256':digest(base)}
    ledger_path.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'patches':len(plan['patches']),'auto_archive_caller_patches':len(plan['patches'])-baseline_count,'accepted_baseline_unchanged':True}))
if __name__=='__main__':main()
