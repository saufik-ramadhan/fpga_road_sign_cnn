# Build the integrated Basys 3 top; does not connect to or program a board.
# vivado -mode batch -source scripts/build_basys3.tcl
set repo [file normalize [file join [file dirname [info script]] ..]]
set package [file join $repo reference_model models p2-doc-int-v2]
set out [file join $repo build basys3]
set weights {conv_weight conv_bias fc_weight fc_bias}
set generics {}
set top top_basys3
set fc 1
if {$argc == 1 && [lindex $argv 0] eq "d42"} {
    set package [file join $repo experiments traffic_sign_d42 models p2-doc-d42-int24-v1]
    set out [file join $repo build basys3_d42]
    lappend weights conv2_weight conv2_bias
    set header [open [file join $package params.vh] r]
    set constants [read $header]
    close $header
    set generics {-generic ENABLE_CONV2=1}
    foreach {key param width} {CONV_M M 16 CONV_S S {} CONV2_M CONV2_M 16 CONV2_S CONV2_S {}} {
        set prefix [expr {$width eq "" ? "" : "${width}'d"}]
        if {![regexp "D42_${key} = ${prefix}(\[0-9\]+);" $constants -> value]} {
            error "Missing D42 constant $key"
        }
        lappend generics -generic "$param=$value"
    }
} elseif {$argc == 1 && [lindex $argv 0] eq "c43"} {
    set package [file join $repo build model_studio packages p2-doc-c43-s44-int24-v1]
    set out [file join $repo build basys3_c43]
    set top top_basys3_c43
} elseif {$argc == 3 && [lindex $argv 0] eq "a-mac"} {
    lassign $argv mode conv fc
    if {$conv ni {1 3 9} || $fc ni {1 2 4 8}} { error "Invalid A MAC configuration" }
    set out [file join $repo build a_mac_${conv}_${fc}]
    set generics [list -generic N_MAC=$conv -generic FC_MAC=$fc]
} elseif {$argc != 0} {
    error "Expected no argument, d42, c43, or a-mac CONV FC"
}
file mkdir $out
foreach name $weights {
    file copy -force [file join $package mem $name.mem] [file join $out $name.mem]
}
file copy -force [file join $package signs.mem] [file join $out signs.mem]
if {$fc > 1} {
    foreach {name stride} {fc_weight 392 fc_bias 1} {
        set source [open [file join $out $name.mem] r]
        set words [split [string trim [read $source]] "\n"]
        close $source
        if {[llength $words] != 8*$stride} { error "Unexpected $name word count" }
        set count [expr {8*$stride/$fc}]
        for {set lane 0} {$lane < $fc} {incr lane} {
            set bank [open [file join $out ${name}_lane${lane}.mem] w]
            puts $bank [join [lrange $words [expr {$lane*$count}] [expr {($lane+1)*$count-1}]] "\n"]
            close $bank
        }
    }
}
cd $out
source [file join $repo rtl read_sources.tcl]
read_xdc [file join $repo constraints basys3.xdc]
if {$top eq "top_basys3_c43"} { read_xdc [file join $repo constraints basys3_c43_clock.xdc] }
synth_design -top $top -part xc7a35tcpg236-1 {*}$generics
foreach port [get_ports] {
    if {[get_property PACKAGE_PIN $port] eq ""} { error "Unconstrained pin: $port" }
    if {[get_property IOSTANDARD $port] ne "LVCMOS33"} { error "Missing I/O standard: $port" }
}
opt_design
place_design
phys_opt_design
route_design
report_utilization -hierarchical -file utilization.txt
report_utilization -file utilization_summary.txt
report_timing_summary -report_unconstrained -file timing.txt
report_drc -file drc.txt
set wns [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
set whs [get_property SLACK [get_timing_paths -max_paths 1 -hold]]
if {$wns < 0 || $whs < 0} { error "Timing failed: setup $wns ns, hold $whs ns" }
write_checkpoint -force top_basys3_routed.dcp
write_bitstream -force top_basys3.bit
puts "Basys 3 build complete: setup $wns ns, hold $whs ns; bitstream in $out"
