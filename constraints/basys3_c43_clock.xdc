# Basys 3 supplies 100 MHz on clk. The stored C-43 core uses 50 MHz.
create_generated_clock -name c43_clk -source [get_ports clk] -divide_by 2 [get_pins u_core_clock/O]
