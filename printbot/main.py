import logging
import os
import uuid
from tempfile import NamedTemporaryFile
from typing import Callable, Collection, Dict, Set, Union

from escpos.printer import Dummy, Usb
from PIL import Image, ImageOps
from telegram import Update
from telegram.ext import CallbackContext, MessageHandler, Updater
from telegram.ext.filters import Filters

logger: logging.Logger = logging.getLogger(__name__)


JsonTypes = Union[str, int, bool]


class POSBot:
    classes: Dict[str, Callable] = {
        "Usb": Usb,
    }

    def __init__(
        self,
        token: str = "",
        printer_class: str = "",
        printer_args: Dict[str, JsonTypes] = {},
        allowed: Collection[int] = [],
    ) -> None:
        self.token = token
        self.printer = self.classes.get(printer_class, Dummy)(**printer_args)
        self.allowed: Set[int] = set(allowed)
        logger.info("POSBot initialized")

    def _acl(f: Callable) -> Callable:  # type: ignore
        def wrapper(self, update: Update, context: CallbackContext) -> None:
            chat_id = update.message.chat_id
            if chat_id not in self.allowed:
                logger.warn("Message from %d was dropped", chat_id)
                return
            f(self, update, context)

        return f

    @_acl
    def _text(self, update: Update, context: CallbackContext) -> None:
        message = update.message.text
        logger.info("Received from %d: %s", update.message.chat_id, message)
        self.printer.textln(message)
        self.printer.cut()

    @_acl
    def _image(self, update: Update, context: CallbackContext) -> None:
        photo = update.message.photo[-1]
        t_imagefile = context.bot.getFile(photo.file_id)
        logger.info("Received image from %d: %s", update.message.chat_id, t_imagefile)
        ext = os.path.splitext(t_imagefile["file_path"])[1]
        with NamedTemporaryFile(suffix=ext) as f:
            imagefile = f.name
            logger.info("Writing to %s", imagefile)
            t_imagefile.download(imagefile)

            try:
                profile = self.printer.profile
                max_width = int(profile.profile_data["media"]["width"]["pixels"])
                image = Image.open(imagefile)
                w, h = image.size
                ar = h / w

                if ar < 1 and h > max_width:
                    logger.info("Rotating image")
                    image = image.rotate(90, expand=True)
                    w, h = image.size
                    ar = h / w

                size = (max_width, int(max_width * ar))
                logger.info("Resizing from %s to %s", image.size, size)
                image.thumbnail(size, Image.ANTIALIAS)

                self.printer.image(image, impl="graphics", center=True)
                del image

                self.printer.cut()
                return
            except KeyError:
                logger.exception("")
            except ValueError:
                logger.exception("")
            else:
                self.printer.image(imagefile)
                self.printer.cut()

    def start(self) -> None:
        updater = Updater(self.token)
        dispatcher = updater.dispatcher
        dispatcher.add_handler(MessageHandler(Filters.text, self._text))
        dispatcher.add_handler(MessageHandler(Filters.photo, self._image))
        updater.start_polling()
        updater.idle()
