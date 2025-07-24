import logging
import os
import uuid
from contextlib import contextmanager
from tempfile import NamedTemporaryFile
from typing import Callable, Collection, Dict, Generator, Set, Union

from escpos.printer import Dummy, Usb
from PIL import Image, ImageOps
from telegram import Update
from telegram.ext import Application, CallbackContext, MessageHandler
import telegram.ext.filters as filters

logger: logging.Logger = logging.getLogger(__name__)


JsonTypes = Union[str, int, bool]
TPrinter = Union[Usb, Dummy]


class POSBot:
    CLASSES: Dict[str, Callable] = {
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
        self.printer_class = self.CLASSES.get(printer_class, Dummy)
        self.printer_args = printer_args
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

    @contextmanager
    def printer(self) -> Generator[TPrinter, None, None]:
        printer: TPrinter = self.printer_class(**self.printer_args)
        try:
            yield printer
        finally:
            printer.close()
            del printer

    @_acl
    async def _text(self, update: Update, context: CallbackContext) -> None:
        message = update.message.text
        logger.info("Received from %d: %s", update.message.chat_id, message)
        with self.printer() as p:
            p.textln(message)
            p.cut()

    @_acl
    async def _image(self, update: Update, context: CallbackContext) -> None:
        photo = update.message.photo[-1]
        t_imagefile = await context.bot.getFile(photo.file_id)
        logger.info("Received image from %d: %s", update.message.chat_id, t_imagefile)
        ext = os.path.splitext(t_imagefile["file_path"])[1]
        with NamedTemporaryFile(suffix=ext) as f, self.printer() as p:
            imagefile = f.name
            logger.info("Writing to %s", imagefile)
            await t_imagefile.download_to_drive(imagefile)

            try:
                max_width = int(p.profile.profile_data["media"]["width"]["pixels"])
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
                image.thumbnail(size, Image.Resampling.LANCZOS)

                p.image(image, impl="graphics", center=True)
                del image

                p.cut()
                return
            except KeyError:
                logger.exception("")
            except ValueError:
                logger.exception("")
            else:
                p.image(imagefile)
                p.cut()

    def start(self) -> None:
        with self.printer() as p:
            logger.info("Printer is %s", p.is_online() and "online" or "offline")

        application = Application.builder().token(self.token).build()
        application.add_handler(MessageHandler(filters.TEXT, self._text))
        application.add_handler(MessageHandler(filters.PHOTO, self._image))
        application.run_polling()
