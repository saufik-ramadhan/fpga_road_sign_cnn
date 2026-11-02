# Read production Verilog sources from the repository-root-relative manifest.
# Source this file from Vivado before reading the project-specific top/XDC.
set road_sign_repo [file normalize [file join [file dirname [info script]] ..]]
set road_sign_filelist [open [file join $road_sign_repo rtl files.f] r]
set road_sign_sources {}
foreach road_sign_line [split [read $road_sign_filelist] "\n"] {
    set road_sign_line [string trim $road_sign_line]
    if {$road_sign_line ne "" && ![string match "#*" $road_sign_line]} {
        set road_sign_path [file join $road_sign_repo $road_sign_line]
        if {![file isfile $road_sign_path]} { error "Missing RTL source: $road_sign_path" }
        lappend road_sign_sources $road_sign_path
    }
}
close $road_sign_filelist
read_verilog $road_sign_sources
