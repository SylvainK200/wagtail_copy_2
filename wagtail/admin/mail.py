import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import get_connection
from django.core.mail.message import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.translation import override

from wagtail.admin.auth import users_with_page_permission
from wagtail.coreutils import camelcase_to_underscore
from wagtail.models import GroupApprovalTask, TaskState, WorkflowState
from wagtail.users.models import UserProfile

logger = logging.getLogger("wagtail.admin")


class OpenedConnection:
    """Context manager for mail connections to ensure they are closed when manually opened"""

    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        self.connection.open()
        return self.connection

    def __exit__(self, type, value, traceback):
        self.connection.close()
        return self.connection


def send_mail(subject, message, recipient_list, from_email=None, **kwargs):
    """
    Wrapper around Django's EmailMultiAlternatives as done in send_mail().
    Custom from_email handling and special Auto-Submitted header.
    """
    if from_email is None:
        from_email = settings.DEFAULT_FROM_EMAIL

    headers = kwargs.pop("headers", None)
    if headers is None:
        headers = {}
    headers["Auto-Submitted"] = "auto-generated"

    email_message = EmailMultiAlternatives(
        subject, message, from_email, recipient_list, headers=headers, **kwargs
    )
    email_message.send()


def send_moderation_notification(revision, notification, excluded_user=None):
    # Get list of recipients
    recipient_users = get_user_model().objects.none()
    if notification == "submitted_for_moderation":
        # Get users with permission to publish
        recipient_users = users_with_page_permission(
            revision.page, permission_type="publish"
        )
    elif notification == "approved_moderation":
        # Get users with permission to edit
        recipient_users = users_with_page_permission(
            revision.page, permission_type="edit"
        )

    # Exclude excluded_user
    if excluded_user:
        recipient_users = recipient_users.exclude(pk=excluded_user.pk)

    # Return if there are no recipients
    if not recipient_users:
        return True

    # Get page title
    page_title = revision.page.get_admin_display_title()

    # Get revision url
    revision_url = revision.page.get_admin_url() + "revisions/" + str(revision.id) + "/"

    # Send notification
    return send_notification(
        recipient_users,
        notification,
        {
            "page": revision.page,
            "page_title": page_title,
            "revision": revision,
            "revision_url": revision_url,
        },
    )


def send_notification(recipient_users, notification, extra_context):
    # Get list of email addresses
    recipient_emails = [
        user.email for user in recipient_users if user.email and user.is_active
    ]

    # Get extra context
    context = {
        "site_name": settings.WAGTAIL_SITE_NAME,
        "protocol": "https" if settings.WAGTAILADMIN_NOTIFICATION_USE_HTTPS else "http",
    }
    context.update(extra_context)

    # Render email
    subject = render_to_string(
        "wagtailadmin/notifications/%s/subject.txt" % notification, context
    )
    # Email subject *must not* contain newlines
    subject = "".join(subject.splitlines())
    body = render_to_string(
        "wagtailadmin/notifications/%s/body.txt" % notification, context
    )

    # Send email
    connection = get_connection()
    if isinstance(connection, OpenedConnection):
        # If the connection is already open, send_mail will close it
        # so we need to open it again
        return send_mail(
            subject, body, recipient_emails, connection=connection, fail_silently=False
        )
    else:
        return send_mail(subject, body, recipient_emails, fail_silently=False)

=======


class Notifier:
    """Generic class for sending event notifications: callable, intended to be connected to a signal to send
    notifications using rendered templates."""

    notification = ""
    template_directory = "wagtailadmin/notifications/"

    def __init__(self, valid_classes):
        # the classes of the calling instance that the notifier can handle
        self.valid_classes = valid_classes

    def can_handle(self, instance, **kwargs):
        """Returns True if the Notifier can handle sending the notification from the instance, otherwise False"""
        return isinstance(instance, self.valid_classes)

    def get_valid_recipients(self, instance, **kwargs):
        """Returns a set of the final list of recipients for the notification message"""
        return set()

    def get_template_base_prefix(self, instance, **kwargs):
        return camelcase_to_underscore(type(instance).__name__) + "_"

    def get_context(self, instance, **kwargs):
        return {"settings": settings}

    def get_template_set(self, instance, **kwargs):
        """Return a dictionary of template paths for the templates: by default, a text message"""
        template_base = self.get_template_base_prefix(instance) + self.notification

        template_text = self.template_directory + template_base + ".txt"

        return {
            "text": template_text,
        }

    def send_notifications(self, template_set, context, recipients, **kwargs):
        raise NotImplementedError

    def __call__(self, instance=None, **kwargs):
        """Send notifications from an instance (intended to be the signal sender), returning True if all sent correctly
        and False otherwise"""

        if not self.can_handle(instance, **kwargs):
            return False

        recipients = self.get_valid_recipients(instance, **kwargs)

        if not recipients:
            return True

        template_set = self.get_template_set(instance, **kwargs)

        context = self.get_context(instance, **kwargs)

        return self.send_notifications(template_set, context, recipients, **kwargs)


class EmailNotificationMixin:
    """Mixin for sending email notifications upon events"""

    def get_recipient_users(self, instance, **kwargs):
        """Gets the ideal set of recipient users, without accounting for notification preferences or missing email addresses"""

        return set()

    def get_valid_recipients(self, instance, **kwargs):
        """Filters notification recipients to those allowing the notification type on their UserProfile, and those
        with an email address"""
        return {
            recipient
            for recipient in self.get_recipient_users(instance, **kwargs)
            if recipient.is_active
            and recipient.email
            and getattr(
                UserProfile.get_for_user(recipient),
                self.notification + "_notifications",
            )
        }

    def get_template_set(self, instance, **kwargs):
        """Return a dictionary of template paths for the templates for the email subject and the text and html
        alternatives"""
        template_base = self.get_template_base_prefix(instance) + self.notification

        template_subject = self.template_directory + template_base + "_subject.txt"
        template_text = self.template_directory + template_base + ".txt"
        template_html = self.template_directory + template_base + ".html"

        return {
            "subject": template_subject,
            "text": template_text,
            "html": template_html,
        }

    def send_emails(self, template_set, context, recipients, **kwargs):
        messages = []

        for recipient in recipients:
            # Render templates
            subject = render_to_string(template_set["subject"], context).strip()
            text_body = render_to_string(template_set["text"], context)
            html_body = render_to_string(template_set["html"], context)

            # Construct message
            message = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient.email],
            )
            message.extra_headers = {"Auto-Submitted": "auto-generated"}
            message.attach_alternative(html_body, "text/html")

            messages.append(message)

        # Send messages
        return connection.send_messages(messages)
        

    def send_notifications(self, template_set, context, recipients, **kwargs):
        return self.send_emails(template_set, context, recipients, **kwargs)


class BaseWorkflowStateEmailNotifier(EmailNotificationMixin, Notifier):
    """A base notifier to send email updates for WorkflowState events"""

    def __init__(self):
        super().__init__((WorkflowState,))

    def get_context(self, workflow_state, **kwargs):
        context = super().get_context(workflow_state, **kwargs)
        context["page"] = workflow_state.page
        context["workflow"] = workflow_state.workflow
        return context


class WorkflowStateApprovalEmailNotifier(BaseWorkflowStateEmailNotifier):
    """A notifier to send email updates for WorkflowState approval events"""

    notification = "approved"

    def get_recipient_users(self, workflow_state, **kwargs):
        triggering_user = kwargs.get("user", None)
        recipients = {}
        requested_by = workflow_state.requested_by
        if requested_by != triggering_user:
            recipients = {requested_by}

        return recipients


class WorkflowStateRejectionEmailNotifier(BaseWorkflowStateEmailNotifier):
    """A notifier to send email updates for WorkflowState rejection events"""

    notification = "rejected"

    def get_recipient_users(self, workflow_state, **kwargs):
        triggering_user = kwargs.get("user", None)
        recipients = {}
        requested_by = workflow_state.requested_by
        if requested_by != triggering_user:
            recipients = {requested_by}

        return recipients

    def get_context(self, workflow_state, **kwargs):
        context = super().get_context(workflow_state, **kwargs)
        task_state = workflow_state.current_task_state.specific
        context["task"] = task_state.task
        context["task_state"] = task_state
        context["comment"] = task_state.get_comment()
        return context


class WorkflowStateSubmissionEmailNotifier(BaseWorkflowStateEmailNotifier):
    """A notifier to send email updates for WorkflowState submission events"""

    notification = "submitted"

    def get_recipient_users(self, workflow_state, **kwargs):
        triggering_user = kwargs.get("user", None)
        recipients = get_user_model().objects.none()
        include_superusers = getattr(
            settings, "WAGTAILADMIN_NOTIFICATION_INCLUDE_SUPERUSERS", True
        )
        if include_superusers:
            recipients = get_user_model().objects.filter(is_superuser=True)
        if triggering_user:
            recipients.exclude(pk=triggering_user.pk)

        return recipients

    def get_context(self, workflow_state, **kwargs):
        context = super().get_context(workflow_state, **kwargs)
        context["requested_by"] = workflow_state.requested_by
        return context


class BaseGroupApprovalTaskStateEmailNotifier(EmailNotificationMixin, Notifier):
    """A base notifier to send email updates for GroupApprovalTask events"""

    def __init__(self):
        super().__init__((TaskState,))

    def can_handle(self, instance, **kwargs):
        if super().can_handle(instance, **kwargs) and isinstance(
            instance.task.specific, GroupApprovalTask
        ):
            return True
        return False

    def get_context(self, task_state, **kwargs):
        context = super().get_context(task_state, **kwargs)
        context["page"] = task_state.workflow_state.page
        context["task"] = task_state.task.specific
        return context

    def get_recipient_users(self, task_state, **kwargs):
        triggering_user = kwargs.get("user", None)

        group_members = get_user_model().objects.filter(
            groups__in=task_state.task.specific.groups.all()
        )

        recipients = group_members

        include_superusers = getattr(
            settings, "WAGTAILADMIN_NOTIFICATION_INCLUDE_SUPERUSERS", True
        )
        if include_superusers:
            superusers = get_user_model().objects.filter(is_superuser=True)
            recipients = recipients | superusers

        if triggering_user:
            recipients = recipients.exclude(pk=triggering_user.pk)

        return recipients


class GroupApprovalTaskStateSubmissionEmailNotifier(
    BaseGroupApprovalTaskStateEmailNotifier
):
    """A notifier to send email updates for GroupApprovalTask submission events"""

    notification = "submitted"
