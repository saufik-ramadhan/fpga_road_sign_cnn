# synth_p3.tcl: out-of-context synthesis, place and route of P3's block
# (conv_engine and fmap_ram) on the Basys3's XC7A35T, for its timing,
# utilisation and power. Run from the repository root:
#
#   vivado -mode batch -nojournal -source tests/rtl/p3/synth_p3.tcl [-tclargs [<n_mac>] [<folder>]]
#
# <n_mac> is conv_engine's number of multipliers, 1 (the default), 3 or 9.
# conv_engine keeps its other default parameters (P2's model p2-doc-int-v2,
# 24-bit accumulator) and loads conv_weight.mem and conv_bias.mem from
# <folder>: a P2 package with 24-bit biases, whose files are in mem/ (default
# reference_model/models/p2-doc-int-v2), or a 24-bit set written by
# run_p3_tests.py such as build/p3_sim/iverilog/conv_model.
# Reports go to build/p3_synth/mac<n_mac>/.

set repo [file normalize [file join [file dirname [info script]] .. .. ..]]
set n_mac 1
set vec [file join $repo reference_model models p2-doc-int-v2]
foreach arg $argv {
    if {[string is integer -strict $arg]} {
        set n_mac $arg
    } else {
        set vec [file normalize $arg]
    }
}
if {[lsearch -exact {1 3 9} $n_mac] < 0} {
    error "N_MAC must be 1, 3 or 9, not $n_mac"
}
if {[file exists [file join $vec mem conv_weight.mem]]} {
    set vec [file join $vec mem]
}
set out  [file join $repo build p3_synth mac$n_mac]
file mkdir $out
file copy -force [file join $vec conv_weight.mem] [file join $vec conv_bias.mem] $out
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

source [file join $repo rtl read_sources.tcl]
read_verilog [list [file join $repo tests rtl p3 p3_synth_top.v]]
read_xdc -mode out_of_context p3_synth_top.xdc
synth_design -top p3_synth_top -part xc7a35tcpg236-1 -mode out_of_context -generic N_MAC=$n_mac
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
set power [report_power -return_string]
regexp {Total On-Chip Power \(W\)\s*\|\s*([0-9.]+)} $power -> total_w
regexp {Dynamic \(W\)\s*\|\s*([0-9.]+)} $power -> dynamic_w
puts [format "P3 block, N_MAC %d, Vivado %s: WNS %.3f ns at 10 ns (about %.0f MHz top speed), %s LUTs, %s FFs, %s BRAM tiles, %s DSPs, %s W on chip (%s W dynamic, vectorless)" \
          $n_mac [version -short] $wns [expr {1000.0 / (10.0 - $wns)}] $count(LUTs) $count(FFs) \
          $count(BRAM) $count(DSPs) $total_w $dynamic_w]
puts "Reports in $out"
