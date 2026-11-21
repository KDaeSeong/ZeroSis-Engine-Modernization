#pragma once
// Source-only x64 ABI migration: all GameCore and provider objects must be rebuilt.
#include <algorithm>
#include <limits>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

namespace CvAutoArchive {
// Immutable interned strings keep name pointers stable across registration removal,
// different construction orders and concurrent construction of independent owners.
inline const std::string* InternName(const std::string& name) {
    struct Pool { std::mutex mutex; std::set<std::string> values; };
    static Pool pool;
    std::lock_guard<std::mutex> guard(pool.mutex);
    return &*pool.values.insert(name).first;
}

template<class Vector> size_t Additional(const Vector& values, size_t count) {
    if (count > values.max_size() - values.size()) throw std::length_error("AutoVector capacity overflow");
    return values.size() + count;
}

template<class Vector> void Reserve(Vector& values, size_t required) {
    if (required > values.max_size()) throw std::length_error("AutoVector capacity overflow");
    if (required <= values.capacity()) return;
    const size_t capacity = values.capacity();
    const size_t increment = (std::min)(capacity / 2 + 1, values.max_size() - capacity);
    values.reserve((std::max)(required, capacity + increment));
}

template<class Element, class Commands, class Owner, class Variable, class Action>
void Mutate(std::vector<Element>& values, Commands& commands, Owner& owner, Variable& variable,
            const typename Commands::value_type& command, size_t required, const Action& action, std::true_type) {
    // For no-throw value types, reserve everything before touch(). This preserves
    // amortized growth instead of copying the complete vector on every scalar edit.
    Reserve(commands, Additional(commands, 1));
    Reserve(values, required);
    owner.touch(variable); // Last potentially allocating operation before commit.
    action(values, command.value);
    commands.push_back(command);
}

template<class Element, class Commands, class Owner, class Variable, class Action>
void Mutate(std::vector<Element>& values, Commands& commands, Owner& owner, Variable& variable,
            const typename Commands::value_type& command, size_t required, const Action& action, std::false_type) {
    std::vector<Element> next(values);
    Commands nextCommands(commands);
    Reserve(next, required);
    action(next, command.value);
    nextCommands.push_back(command);
    owner.touch(variable);
    values.swap(next);
    commands.swap(nextCommands);
}

template<class Element, class Commands, class Owner, class Variable, class Action>
void Mutate(std::vector<Element>& values, Commands& commands, Owner& owner, Variable& variable,
            const typename Commands::value_type& command, size_t required, const Action& action) {
    typedef std::integral_constant<bool, std::is_nothrow_copy_constructible<Element>::value
        && std::is_nothrow_copy_assignable<Element>::value && std::is_nothrow_default_constructible<Element>::value
        && std::is_nothrow_destructible<Element>::value> Fast;
    Mutate(values, commands, owner, variable, command, required, action, Fast());
}

template<class Element, class Commands, class Owner, class Variable>
void Assign(std::vector<Element>& values, Commands& commands, Owner& owner, Variable& variable,
            const std::vector<Element>& input, unsigned char clearCode, unsigned char pushCode) {
    std::vector<Element> next(input); // Handles input aliasing the current vector.
    Commands nextCommands(commands);
    typename Commands::value_type command;
    command.command = clearCode;
    nextCommands.push_back(command);
    for (typename std::vector<Element>::const_iterator it = next.begin(); it != next.end(); ++it) {
        command.command = pushCode;
        command.value = *it;
        nextCommands.push_back(command);
    }
    owner.touch(variable);
    values.swap(next);
    commands.swap(nextCommands);
}
}
