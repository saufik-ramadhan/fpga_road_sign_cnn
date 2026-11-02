# Build the integrated Basys 3 top; does not connect to or program a board.
# vivado -mode batch -source scripts/build_basys3.tcl
set repo [file normalize [file join [file dirname [info script]] ..]]
set package [file join $repo reference_model models p2-doc-int-v2]
set out [file join $repo build basys3]
file mkdir $out
foreach name {conv_weight conv_bias fc_weight fc_bias} {
    file copy -force [file join $package mem $name.mem] [file join $out $name.mem]
}
file copy -force [file join $package signs.mem] [file join $out signs.mem]
cd $out
source [file join $repo rtl read_sources.tcl]
read_xdc [file join $repo constraints basys3.xdc]
synth_design -top top_basys3 -part xc7a35tcpg236-1
foreach port [get_ports] {
    if {[get_property PACKAGE_PIN $port] eq ""} { error "Unconstrained pin: $port" }
    if {[get_property IOSTANDARD $port] ne "LVCMOS33"} { error "Missing I/O standard: $port" }
}
opt_design
place_design
phys_opt_design
route_design
report_utilization -hierarchical -file utilization.txt
report_timing_summary -report_unconstrained -file timing.txt
report_drc -file drc.txt
set wns [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
set whs [get_property SLACK [get_timing_paths -max_paths 1 -hold]]
if {$wns < 0 || $whs < 0} { error "Timing failed: setup $wns ns, hold $whs ns" }
write_checkpoint -force top_basys3_routed.dcp
write_bitstream -force top_basys3.bit
puts "Basys 3 build complete: setup $wns ns, hold $whs ns; bitstream in $out"
