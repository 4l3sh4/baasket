namespace Baasket.LogisticsV2;

/// <summary>
/// Generates and attaches a <see cref="CheckoutReceipt"/> when payment is confirmed.
/// </summary>
public sealed class ReceiptGeneratorObserver : IObserver
{
    public void Update(CheckoutSession session, CheckoutSessionState previousState)
    {
        if (previousState != CheckoutSessionState.CheckoutStarted
            || session.State != CheckoutSessionState.PaymentConfirmed)
        {
            return;
        }

        var issuedAt = session.PaymentConfirmedAtUtc ?? DateTime.UtcNow;
        var receipt = new CheckoutReceipt(
            Reference: session.PaymentReference,
            BuyerName: session.BuyerName,
            BuyerEmail: session.BuyerEmail,
            PaymentMethod: session.PaymentMethod,
            Subtotal: session.Subtotal,
            Fee: session.Fee,
            Total: session.Total,
            IssuedAtUtc: issuedAt,
            Message: $"{CheckoutSessionStateDisplay.Display(CheckoutSessionState.PaymentConfirmed)} — payment approved for {session.BuyerName}.");

        session.RecordReceipt(receipt);
    }
}
