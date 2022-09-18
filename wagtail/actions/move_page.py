import logging

from django.core.exceptions import PermissionDenied
from django.db import transaction
from treebeard.mp_tree import MP_MoveHandler

from wagtail.log_actions import log
from wagtail.signals import post_page_move, pre_page_move

logger = logging.getLogger("wagtail")


class MovePagePermissionError(PermissionDenied):
    """
    Raised when the page move cannot be performed due to insufficient permissions.
    """

    pass


class MovePageAction:
    def __init__(self, page, target, pos=None, user=None):
        self.page = page
        self.target = target
        self.pos = pos
        self.user = user

    def check(self, parent_after, skip_permission_checks=False):
        if self.user and not skip_permission_checks:
            if not self.page.permissions_for_user(self.user).can_move_to(parent_after):
                raise MovePagePermissionError(
                    "You do not have permission to move the page to the target specified."
                )

    def _move_page(self, page, target, parent_after):
        from wagtail.models import Page

        # Determine old and new url_paths
        # Fetching new object to avoid affecting `page`
        new = Page.objects.get(id=page.id)
        old_url_path = page.url_path
        new_url_path = new.get_url_path(parent_after)

        # Move the page
        with transaction.atomic():
            pre_page_move.send(sender=self.__class__, instance=page, target=target, pos=self.pos)

            MP_MoveHandler.move(page, target, pos=self.pos)

            post_page_move.send(
                sender=self.__class__, instance=page, target=target, pos=self.pos
            )

        # Log the action
        log(
            "wagtail.pages.move",
            page,
            user=self.user,
            data={
                "title": page.get_admin_display_title(),
                "old_url_path": old_url_path,
                "new_url_path": new_url_path,
            },
        )

        # Update descendants' url_paths
        page.update_descendants_url_paths(old_url_path, new_url_path)

        return page
    def execute(self, skip_permission_checks=False):
        if self.pos in ("first-child", "last-child", "sorted-child"):
            parent_after = self.target
        else:
            parent_after = self.target.get_parent()

        self.check(parent_after, skip_permission_checks=skip_permission_checks)

        return self._move_page(self.page, self.target, parent_after)
