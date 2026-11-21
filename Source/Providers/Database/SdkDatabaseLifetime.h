#pragma once
// Registry access is synchronized across independent connections. Operations on one
// Connection/Results still require caller serialization, including Close/destruction.
namespace Database {
void TrackCommand(const Connection* owner,Command* command);
void UntrackCommand(const Connection* owner,Command* command);
void DetachCommands(const Connection* owner);
void SwapCommands(Command& left,Command& right);
}
