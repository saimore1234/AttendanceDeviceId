def execute():
	from attendance_device_integration.device_adapters.registry import DEVICE_ADAPTERS, create_adapter, get_adapter_class
	from attendance_device_integration.device_adapters.base import AdapterError

	print("All adapter modules imported OK")

	for protocol_type, adapter_class in DEVICE_ADAPTERS.items():
		caps = adapter_class.capabilities()
		print(f"{protocol_type:32s} -> {adapter_class.__name__:20s} get_users={caps['get_users']:10s} get_attendance_logs={caps['get_attendance_logs']}")

	# Unknown protocol type raises cleanly
	try:
		get_adapter_class("Carrier Pigeon")
		raise AssertionError("expected AdapterError")
	except AdapterError:
		pass

	# Generic TCP adapter: no IP configured -> clear error, not a crash
	tcp = create_adapter({"protocol_type": "Generic TCP/IP"})
	try:
		tcp.connect()
		raise AssertionError("expected AdapterError for missing IP")
	except AdapterError as e:
		assert e.error_code == "INVALID_IP", e.error_code

	print("All smoke assertions passed")
