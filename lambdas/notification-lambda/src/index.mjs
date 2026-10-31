import { SESv2Client, SendEmailCommand } from "@aws-sdk/client-sesv2";

const region = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || "us-east-1";
const fromEmail = process.env.SES_FROM_EMAIL;
const fallbackRecipient = process.env.SES_TO_EMAIL || fromEmail;

const ses = new SESv2Client({ region });

export const handler = async (event) => {
  if (!fromEmail) {
    throw new Error("SES_FROM_EMAIL is required.");
  }

  const batchItemFailures = [];

  for (const record of event.Records ?? []) {
    try {
      await processRecord(record);
    } catch (error) {
      console.error("Failed to process notification record", {
        messageId: record.messageId,
        errorMessage: error instanceof Error ? error.message : String(error),
      });

      batchItemFailures.push({
        itemIdentifier: record.messageId,
      });
    }
  }

  return { batchItemFailures };
};

async function processRecord(record) {
  const envelope = parseEnvelope(record);

  switch (envelope.eventType) {
    case "TrackingStatusUpdated":
      await sendTrackingStatusUpdatedEmail(envelope);
      return;
    default:
      console.warn("Skipping unsupported notification event", {
        messageId: record.messageId,
        eventType: envelope.eventType,
      });
  }
}

function parseEnvelope(record) {
  if (!record.body) {
    throw new Error("SQS record body was empty.");
  }

  const envelope = JSON.parse(record.body);

  if (!envelope?.eventId || !envelope?.eventType || !envelope?.data) {
    throw new Error("Notification event envelope is invalid.");
  }

  return envelope;
}

async function sendTrackingStatusUpdatedEmail(envelope) {
  const data = envelope.data;

  if (!data.shipmentId || !data.status || !data.location || !data.eventOccurredAt) {
    throw new Error("TrackingStatusUpdated event data is incomplete.");
  }

  const recipients = resolveRecipients(data);
  const subject = `Shipment update: ${data.status}`;
  const textBody = [
    `Shipment ${data.shipmentId} has a new tracking update.`,
    `Status: ${data.status}`,
    `Location: ${data.location}`,
    `Occurred At: ${data.eventOccurredAt}`,
    `Tracking Event Id: ${data.trackingEventId ?? "n/a"}`,
  ].join("\n");

  const htmlBody = `
    <h1>Shipment update</h1>
    <p>Shipment <strong>${escapeHtml(data.shipmentId)}</strong> has a new tracking update.</p>
    <ul>
      <li>Status: <strong>${escapeHtml(data.status)}</strong></li>
      <li>Location: <strong>${escapeHtml(data.location)}</strong></li>
      <li>Occurred At: <strong>${escapeHtml(data.eventOccurredAt)}</strong></li>
      <li>Tracking Event Id: <strong>${escapeHtml(data.trackingEventId ?? "n/a")}</strong></li>
    </ul>
  `;

  await sendEmail({
    eventId: envelope.eventId,
    eventType: envelope.eventType,
    recipients,
    subject,
    textBody,
    htmlBody,
  });
}

function resolveRecipients(data) {
  if (Array.isArray(data.recipients) && data.recipients.length > 0) {
    return data.recipients;
  }

  if (!fallbackRecipient) {
    throw new Error("No recipient email address is configured.");
  }

  return [fallbackRecipient];
}

async function sendEmail({ eventId, eventType, recipients, subject, textBody, htmlBody }) {
  const command = new SendEmailCommand({
    FromEmailAddress: fromEmail,
    Destination: {
      ToAddresses: recipients,
    },
    Content: {
      Simple: {
        Subject: {
          Data: subject,
          Charset: "UTF-8",
        },
        Body: {
          Text: {
            Data: textBody,
            Charset: "UTF-8",
          },
          Html: {
            Data: htmlBody,
            Charset: "UTF-8",
          },
        },
      },
    },
  });

  const response = await ses.send(command);

  console.info("Notification email sent", {
    eventId,
    eventType,
    messageId: response.MessageId,
    recipients,
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
