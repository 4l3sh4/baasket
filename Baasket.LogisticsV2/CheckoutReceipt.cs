namespace Baasket.LogisticsV2;

/// <summary>
/// Immutable receipt produced after payment confirmation.
/// Maps to the existing Python <c>PaymentReceipt</c> concept.
/// </summary>
public sealed record CheckoutReceipt(
    string Reference,
    string BuyerName,
    string BuyerEmail,
    string PaymentMethod,
    decimal Subtotal,
    decimal Fee,
    decimal Total,
    DateTime IssuedAtUtc,
    string Message);
