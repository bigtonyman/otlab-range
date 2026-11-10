#!/bin/bash
# otlab: adapted from virtual-factory OpenPLC/entrypoint.sh. Differences: python3 venv instead of python2.7,
# idempotent database setup, no `wait`. Program and device config are mounted at /OpenPLC_v3/scripts/config.
set -euo pipefail
DB=/OpenPLC_v3/webserver/openplc.db
CFG=/OpenPLC_v3/scripts/config
sqlite3 "$DB" "DELETE FROM Programs; DELETE FROM Slave_dev;"
sqlite3 "$DB" "INSERT INTO Programs (Name, Description, File, Date_upload) VALUES ('Program Name', 'Desc', 'script.st', strftime('%s', 'now'));"
for file in $(find "$CFG/devices" -type f -name '*.cfg'); do
  echo "device: $file"
  ( . "$file"
    sqlite3 "$DB" "INSERT INTO Slave_dev (dev_name, dev_type, slave_id, ip_address, ip_port, di_start, di_size, coil_start, coil_size, ir_start, ir_size, hr_read_start, hr_read_size, hr_write_start, hr_write_size, baud_rate, parity, data_bits, stop_bits, pause) VALUES ('$name', '$protocol', $slave_id, '$address', $IP_Port, $Discrete_Inputs_Start, $Discrete_Inputs_Size, $Coils_Start, $Coils_Size, $Input_Registers_Start, $Input_Registers_Size, $Holding_Registers_Read_Start, $Holding_Registers_Read_Size, $Holding_Registers_Start, $Holding_Registers_Size, $baud_rate, '$parity', $data_bits, $stop_bits, $pause);" )
done
sqlite3 "$DB" "UPDATE Settings SET Value = 'true' WHERE Key = 'Start_run_mode';"
echo script.st > /OpenPLC_v3/webserver/active_program
cp "$CFG/script.st" /OpenPLC_v3/webserver/st_files/script.st
cd /OpenPLC_v3/webserver/scripts && ./compile_program.sh script.st
cd /OpenPLC_v3/webserver && /OpenPLC_v3/.venv/bin/python3 -c 'import webserver; webserver.generate_mbconfig()'
cd /OpenPLC_v3 && exec ./start_openplc.sh
