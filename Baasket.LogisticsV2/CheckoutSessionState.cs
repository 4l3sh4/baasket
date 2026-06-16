namespace Baasket.LogisticsV2;

/// <summary>
/// Lifecycle states for checkout → payment → logistics tracking.
/// </summary>
public enum CheckoutSessionState
{
    CheckoutStarted = 0,
    PaymentConfirmed = 1,
    Packed = 2,
    Shipped = 3,
    Delivered = 4,
}

public static class CheckoutSessionStateDisplay
{
    public static string Emoji(CheckoutSessionState state) => state switch
    {
        CheckoutSessionState.PaymentConfirmed => "💳",
        CheckoutSessionState.Packed => "📦",
        CheckoutSessionState.Shipped => "🚚",
        CheckoutSessionState.Delivered => "✅",
        _ => "🛒",
    };

    public static string Label(CheckoutSessionState state) => state switch
    {
        CheckoutSessionState.CheckoutStarted => "Checkout started",
        CheckoutSessionState.PaymentConfirmed => "Paid",
        CheckoutSessionState.Packed => "Packed",
        CheckoutSessionState.Shipped => "Shipped",
        CheckoutSessionState.Delivered => "Delivered",
        _ => state.ToString(),
    };

    public static string Display(CheckoutSessionState state) =>
        $"{Emoji(state)} {Label(state)}";
}
