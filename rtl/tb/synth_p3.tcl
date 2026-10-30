# synth_p3.tcl: out-of-context synthesis, place and route of P3's block
# (conv_engine and fmap_ram) on the Basys3's XC7A35T, for its timing,
# utilisation and power. Run from the repository root:
#
#   vivado -mode batch -nojournal -source rtl/tb/synth_p3.tcl -tclargs <folder>
#
# <folder> holds params.vh and conv_weights.mem: P2's files, or a set written by
# run_p3_tests.py such as build/p3_sim/iverilog/conv_model.
# Reports go to build/p3_synth/.

set repo [file normalize [file join [file dirname [info script]] .. ..]]
set vec  [file normalize [lindex $argv 0]]
set out  [file join $repo build p3_synth]
file mkdir $out
file copy -force [file join $vec params.vh] [file join $vec conv_weights.mem] $out
cd $out

# 100 MHz. pix_data comes from P5's block RAM through input_mux: about 2.5 ns of
# clock-to-out plus the mux and routing. pix_addr goes back through input_mux
# to that block RAM's address setup. The controller and maxpool are registered.
set fh [open p3_synth_top.xdc w]
puts $fh {create_clock -period 10.000 -name clk [get_ports clk]
set_input_delay  -clock clk 3.000 [get_ports {pix_data[*]}]
set_output_delay -clock clk 2.500 [get_ports {pix_addr[*] pix_rd}]
set_input_delay  -clock clk 1.000 [get_ports {start rst rd_addr[*]}]
set_output_delay -clock clk 1.000 [get_ports {busy done ovf rd_data[*]}]}
close $fh

set rtl [file join $repo rtl]
read_verilog [list $rtl/conv_wrom.v $rtl/requant_relu.v $rtl/conv_engine.v $rtl/fmap_ram.v \
                   $rtl/tb/p3_synth_top.v]
read_xdc -mode out_of_context p3_synth_top.xdc
synth_design -top p3_synth_top -part xc7a35tcpg236-1 -mode out_of_context -include_dirs $out
opt_design
place_design
route_design

report_utilization -hierarchical -file utilization_hier.txt
report_utilization -file utilization.txt
report_timing_summary -max_paths 5 -file timing.txt
report_power -file power.txt

set wns [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
set util [report_utilization -return_string]
foreach {name pattern} {LUTs {Slice LUTs\s*\|\s*([0-9.]+)} FFs {Slice Registers\s*\|\s*([0-9.]+)}
                        BRAM {Block RAM Tile\s*\|\s*([0-9.]+)} DSPs {DSPs\s*\|\s*([0-9.]+)}} {
    regexp $pattern $util -> count($name)
}
puts [format "P3 block: WNS %.3f ns at 10 ns (about %.0f MHz top speed), %s LUTs, %s FFs, %s BRAM tiles, %s DSPs" \
          $wns [expr {1000.0 / (10.0 - $wns)}] $count(LUTs) $count(FFs) $count(BRAM) $count(DSPs)]
puts "Reports in $out"
