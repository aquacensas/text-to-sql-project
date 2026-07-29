'''Centralized logging configuration for the entire application'''
import logging
import logging
import sys
import os

def get_logger(name:str)->logging.Logger:
    '''Creates and returns a configured logger for a module'''
    logger=logging.getLogger(name)

    if not logger.handlers:
        log_level_str=os.getenv('LOG_LEVEL','INFO').upper()
        log_level=getattr(logging,log_level_str,logging.INFO)
        logger.setLevel(log_level)

        handler=logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)

        formatter=logging.Formatter(
            fmt="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        handler.setFormatter(formatter)
        logger.addHandler(handler)

        logger.propagate=False #Prevents log message from propogating to the root logger
    return logger


