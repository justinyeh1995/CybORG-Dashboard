import json

from CybORG.Emulator.Velociraptor.Actions.ProcessListingAction import ProcessListingAction
from CybORG.Emulator.Velociraptor.Actions.KillProcessAction import KillProcessAction
from CybORG.Emulator.Velociraptor.Actions.RunProcessAction import RunProcessAction
from CybORG.Emulator.Velociraptor.Actions.VelociraptorInterace import VelociraptorInterface

credentials_file = "prog_client.yaml"

create_foobar_action = RunProcessAction(
    credentials_file=credentials_file,
    hostname="TESTDOCKER1", command="""
cat > FOOBAR.sh <<END
while true; do
    sleep 10
done > /dev/null 2>&1
END
"""
)

create_foobar_observation = create_foobar_action.execute(None)

velociraptor_interface = VelociraptorInterface.get_velociraptor_interface(credentials_file)

foo = velociraptor_interface.get_server_glob()

foo_json = json.dumps(foo, sort_keys=True, indent=4)
print(foo_json)
run_foobar_action = RunProcessAction(
    credentials_file=credentials_file, hostname="TESTDOCKER1", command="bash FOOBAR.sh > /dev/null 2>&1 &"
)

run_foobar_observation = run_foobar_action.execute(None)

process_listing_action = ProcessListingAction(
    credentials_file=credentials_file,
    hostname="TESTDOCKER1"
)

process_listing_observation = process_listing_action.execute(None)

process_list = process_listing_observation.get_process_list()
for process in process_list:
    if "FOOBAR" in process.CommandLine:
        kill_process_action = KillProcessAction(
            credentials_file="prog_client.yaml",
            hostname="TESTDOCKER1",
            pid=process.Pid
        )

        kill_process_observation = kill_process_action.execute(None)
        print()