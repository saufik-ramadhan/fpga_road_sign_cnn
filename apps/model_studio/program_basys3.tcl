if {$argc != 1} { error "Supply one validated bitstream path" }
set bit [file normalize [lindex $argv 0]]
open_hw_manager
connect_hw_server
set targets [get_hw_targets]
if {[llength $targets] != 1} { error "Expected one local JTAG target" }
current_hw_target [lindex $targets 0]
open_hw_target
set devices [get_hw_devices -filter {PART == "xc7a35t"}]
if {[llength $devices] != 1} { error "Expected one XC7A35T device" }
set device [lindex $devices 0]
set_property PROGRAM.FILE $bit $device
program_hw_devices $device
refresh_hw_device $device
puts "PROGRAMMED $bit"
close_hw_target
disconnect_hw_server
close_hw_manager
