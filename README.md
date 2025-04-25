# octopus-corelibs-logging

Basic classes for logging setting.

This class only contain one file called Logging.py and one function called setup_logging

### setup_logging
Used to generalize the logging setting. Before use any logging in the application, this function need 
to be executed first.

### Logging style
Here is the format that is used for logging: <br>
[timestamp] [severity] message

and here is the example:<br>
[2025-04-25 06:24:01,817] [INFO] Test message

### Log level
Log level for the application need to be set up in the env variable called LOG_LEVEL. The LOG_LEVEL must be DEBUG, INFO, WARNING, 
ERROR, CRITICAL. The default value is DEBUG.