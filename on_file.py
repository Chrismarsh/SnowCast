class Notifier(object):
    def __init__(self):
        pass

    def on_file(self,parent):
        logger = parent.logger

        logger.info("Downloaded file " + parent.msg.new_file)

        return True

self.plugin = 'Notifier'