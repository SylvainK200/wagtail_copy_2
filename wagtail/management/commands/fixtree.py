import functools
import operator

from django.core.management.base import BaseCommand
from django.db import models
from django.db.models import Q

from wagtail.models import Collection, Page


class Command(BaseCommand):
    help = "Checks for data integrity errors on the page tree, and fixes them where possible."
    stealth_options = ("delete_orphans",)

    def add_arguments(self, parser):
        parser.add_argument(
            "--noinput",
            action="store_false",
            dest="interactive",
            default=True,
            help="If provided, any fixes requiring user interaction will be skipped.",
        )
        parser.add_argument(
            "--full",
            action="store_true",
            dest="full",
            default=False,
            help="If provided, uses a more thorough but slower method that also fixes path ordering issues.",
        )

    def numberlist_to_string(self, numberlist):
        # Converts a list of numbers into a string
        # Doesn't put "L" after longs
        return "[" + ", ".join(map(str, numberlist)) + "]"

    def handle(self, **options):
        interactive = options["interactive"]
        full = options["full"]

        # Check for orphans
        # An orphan is a page that has no parent (i.e. it's not the root page)
        # and also has no children. This means that it's effectively unreachable
        # from the root page, and it will never be shown in the page explorer
        orphans = Page.objects.filter(depth=2, numchild=0)
        if orphans.exists():
            self.stdout.write(
                "The following pages are orphans and will be deleted: %s"
                % self.numberlist_to_string(orphans.values_list("id", flat=True))
            )
            if interactive:
                if input("Are you sure you want to delete these pages? (y/n) ") == "y":
                    orphans.delete()
            else:
                orphans.delete()

        # Check for pages with invalid paths
        # A page with an invalid path is one where the path field does not match
        # the actual path of the page in the tree. This can happen when pages are
        # moved or deleted, but the path field is not updated to reflect the
        # change
        if full:
            invalid_paths = Page.objects.filter(depth__gt=2).exclude(
                path=models.F("parent__path") + models.F("parent__id").astype("text")
            )

            if invalid_paths.exists():
                self.stdout.write(
                    "The following pages have invalid paths and will be fixed: %s"
                    % self.numberlist_to_string(
                        invalid_paths.values_list("id", flat=True)
                    )
                )
                if interactive:
                    if input("Are you sure you want to fix these pages? (y/n) ") == "y":
                        for page in invalid_paths:
                            page.update_path()
                else:
                    for page in invalid_paths:
                        page.update_path()

        # Check for pages with invalid depths
        # A page with an invalid depth is one where the depth field does not match
        # the actual depth of the page in the tree. This can happen when pages are
        # moved or deleted, but the depth field is not updated to reflect the
        # change
        if full:
            invalid_depths = Page.objects.filter(
                depth__gt=1
            ).exclude(depth=models.F("parent__depth") + 1)

            if invalid_depth


    def handle_model(
        self, model, model_name, model_name_plural, any_problems_fixed, options
    ):
        fix_paths = options.get("full", False)

        self.stdout.write("Checking %s tree for problems..." % model_name)
        (bad_alpha, bad_path, orphans, bad_depth, bad_numchild) = model.find_problems()

        if bad_depth:
            self.stdout.write(
                "Incorrect depth value found for %s: %s"
                % (model_name_plural, self.numberlist_to_string(bad_depth))
            )
        if bad_numchild:
            self.stdout.write(
                "Incorrect numchild value found for %s: %s"
                % (model_name_plural, self.numberlist_to_string(bad_numchild))
            )

        if orphans:
            # The 'orphans' list as returned by treebeard only includes nodes that are
            # missing an immediate parent; descendants of orphans are not included.
            # Deleting only the *actual* orphans is a bit silly (since it'll just create
            # more orphans), so generate a queryset that contains descendants as well.
            orphan_paths = model.objects.filter(id__in=orphans).values_list(
                "path", flat=True
            )
            filter_conditions = []
            for path in orphan_paths:
                filter_conditions.append(Q(path__startswith=path))

            # combine filter_conditions into a single ORed condition
            final_filter = functools.reduce(operator.or_, filter_conditions)

            # build a queryset of all nodes to be removed; this must be a vanilla Django
            # queryset rather than a treebeard MP_NodeQuerySet, so that we bypass treebeard's
            # custom delete() logic that would trip up on the very same corruption that we're
            # trying to fix here.
            nodes_to_delete = models.query.QuerySet(model).filter(final_filter)

            self.stdout.write("Orphaned %s found:" % model_name_plural)
            for node in nodes_to_delete:
                self.stdout.write("ID %d: %s" % (node.id, node))
            self.stdout.write("")

            if options.get("interactive", True):
                yes_or_no = input("Delete these %s? [y/N] " % model_name_plural)
                delete_orphans = yes_or_no.lower().startswith("y")
                self.stdout.write("")
            else:
                # Running tests, check for the "delete_orphans" option
                delete_orphans = options.get("delete_orphans", False)

            if delete_orphans:
                deletion_count = len(nodes_to_delete)
                nodes_to_delete.delete()
                self.stdout.write(
                    "%d orphaned %s deleted."
                    % (
                        deletion_count,
                        model_name_plural if deletion_count != 1 else model_name,
                    )
                )
                any_problems_fixed = True

        # fix_paths will fix problems not identified by find_problems, so if that option has been
        # passed, run it regardless (and set any_problems_fixed=True, since we don't have a way to
        # test whether anything was actually fixed in that process)
        if bad_depth or bad_numchild or fix_paths:
            model.fix_tree(destructive=False, fix_paths=fix_paths)
            any_problems_fixed = True

        if any_problems_fixed:
            # re-run find_problems to see if any new ones have surfaced
            (
                bad_alpha,
                bad_path,
                orphans,
                bad_depth,
                bad_numchild,
            ) = model.find_problems()

        if any((bad_alpha, bad_path, orphans, bad_depth, bad_numchild)):
            self.stdout.write("Remaining problems (cannot fix automatically):")
            if bad_alpha:
                self.stdout.write(
                    "Invalid characters found in path for %s: %s"
                    % (model_name_plural, self.numberlist_to_string(bad_alpha))
                )
            if bad_path:
                self.stdout.write(
                    "Invalid path length found for %s: %s"
                    % (model_name_plural, self.numberlist_to_string(bad_path))
                )
            if orphans:
                self.stdout.write(
                    "Orphaned %s found: %s"
                    % (model_name_plural, self.numberlist_to_string(orphans))
                )
            if bad_depth:
                self.stdout.write(
                    "Incorrect depth value found for %s: %s"
                    % (model_name_plural, self.numberlist_to_string(bad_depth))
                )
            if bad_numchild:
                self.stdout.write(
                    "Incorrect numchild value found for %s: %s"
                    % (model_name_plural, self.numberlist_to_string(bad_numchild))
                )

        elif any_problems_fixed:
            self.stdout.write("All problems fixed.\n\n")
        else:
            self.stdout.write("No problems found.\n\n")
