import React, { useState } from 'react';
import {
  Container,
  Typography,
  Box,
  Button,
  Grid,
  Paper,
  Divider,
  TextField,
  Alert,
  CardMedia,
  CircularProgress,
  Breadcrumbs,
  Link,
} from '@mui/material';
import {
  CheckCircle as SuccessIcon,
  ShoppingBag as ShoppingBagIcon,
  Security as SecurityIcon,
  LocalShipping as ShippingIcon,
  ArrowBack as ArrowBackIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useCart } from '../../contexts/CartContext';
import { useAuth } from '../../contexts/AuthContext';
import { orderService } from '../../services/orderService';
import { Order } from '../../types';

const Checkout: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { items, total, clearCart } = useCart();

  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [completedOrder, setCompletedOrder] = useState<Order | null>(null);

  const [address, setAddress] = useState({
    fullName: user ? `${user.firstName || ''} ${user.lastName || ''}`.trim() : '',
    street: '100 Innovation Way, Suite 400',
    city: 'Columbus',
    state: 'OH',
    zipCode: '43215',
    country: 'United States',
  });

  const subtotal = total;
  const shipping = subtotal > 500 ? 0 : 15;
  const tax = subtotal * 0.08;
  const finalTotal = subtotal + shipping + tax;

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setAddress(prev => ({ ...prev, [name]: value }));
  };

  const handlePlaceOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (items.length === 0) return;

    setSubmitting(true);
    setErrorMessage(null);

    try {
      const orderPayload = {
        items: items.map(item => ({
          productId: item.id,
          quantity: item.quantity,
        })),
        shippingAddress: {
          fullName: address.fullName,
          street: address.street,
          city: address.city,
          state: address.state,
          zipCode: address.zipCode,
          country: address.country,
        },
      };

      const order = await orderService.createOrder(orderPayload);
      clearCart();
      setCompletedOrder(order);
    } catch (err: any) {
      const msg = err.response?.data?.error || err.message || 'Failed to place order. Please try again.';
      setErrorMessage(msg);
    } finally {
      setSubmitting(false);
    }
  };

  // 1. Order Completion Screen
  if (completedOrder) {
    return (
      <Container maxWidth="md" sx={{ py: 6 }}>
        <Paper elevation={3} sx={{ p: 4, textAlign: 'center', borderRadius: 3 }}>
          <SuccessIcon sx={{ fontSize: 72, color: 'success.main', mb: 2 }} />
          <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 700 }}>
            Order Confirmed!
          </Typography>
          <Typography variant="h6" color="text.secondary" paragraph>
            Thank you for your purchase, {address.fullName}.
          </Typography>
          <Alert severity="success" sx={{ my: 3, textAlign: 'left' }}>
            <strong>Order Placed Successfully:</strong> Your order has been confirmed and inventory reserved.
            <br />
            <strong>Order Reference ID:</strong> <code>{completedOrder.id}</code>
            <br />
            <strong>Total Amount:</strong> ${completedOrder.totalAmount?.toFixed(2)}
            <br />
            <strong>Status:</strong> {completedOrder.status?.toUpperCase()}
          </Alert>
          <Box sx={{ mt: 4, display: 'flex', gap: 2, justifyContent: 'center' }}>
            <Button
              variant="contained"
              size="large"
              onClick={() => navigate('/orders')}
              sx={{ px: 4 }}
            >
              View in Order History
            </Button>
            <Button
              variant="outlined"
              size="large"
              onClick={() => navigate('/products')}
              sx={{ px: 4 }}
            >
              Continue Shopping
            </Button>
          </Box>
        </Paper>
      </Container>
    );
  }

  // 2. Empty Cart Check
  if (items.length === 0) {
    return (
      <Container maxWidth="md" sx={{ py: 8, textAlign: 'center' }}>
        <ShoppingBagIcon sx={{ fontSize: 72, color: 'text.secondary', mb: 2 }} />
        <Typography variant="h4" gutterBottom>
          Your Cart is Empty
        </Typography>
        <Typography variant="body1" color="text.secondary" paragraph>
          Please select products from our boutique catalog before initiating checkout.
        </Typography>
        <Button variant="contained" onClick={() => navigate('/products')}>
          Explore Products
        </Button>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Breadcrumbs sx={{ mb: 3 }}>
        <Link component="button" variant="body2" onClick={() => navigate('/')}>
          Home
        </Link>
        <Link component="button" variant="body2" onClick={() => navigate('/cart')}>
          Cart
        </Link>
        <Typography variant="body2" color="text.primary">
          Checkout
        </Typography>
      </Breadcrumbs>

      <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 700 }}>
        Checkout
      </Typography>

      <Alert severity="info" sx={{ mb: 4 }}>
        <strong>COMPLIMENTARY EXPRESS CHECKOUT</strong>
        <br />
        Boutique membership courtesy authorization enabled. Complimentary insured express delivery on all orders.
      </Alert>

      {errorMessage && (
        <Alert severity="error" sx={{ mb: 4 }} onClose={() => setErrorMessage(null)}>
          {errorMessage}
        </Alert>
      )}

      <form onSubmit={handlePlaceOrder}>
        <Grid container spacing={4}>
          {/* Shipping Form */}
          <Grid size={{ xs: 12, md: 7 }}>
            <Paper elevation={2} sx={{ p: 3, mb: 3 }}>
              <Typography variant="h5" gutterBottom sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 1 }}>
                <ShippingIcon /> Shipping Address
              </Typography>
              <Divider sx={{ mb: 3 }} />

              <Grid container spacing={2}>
                <Grid size={{ xs: 12 }}>
                  <TextField
                    required
                    fullWidth
                    label="Recipient Full Name"
                    name="fullName"
                    value={address.fullName}
                    onChange={handleInputChange}
                  />
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <TextField
                    required
                    fullWidth
                    label="Street Address"
                    name="street"
                    value={address.street}
                    onChange={handleInputChange}
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 6 }}>
                  <TextField
                    required
                    fullWidth
                    label="City"
                    name="city"
                    value={address.city}
                    onChange={handleInputChange}
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 3 }}>
                  <TextField
                    required
                    fullWidth
                    label="State"
                    name="state"
                    value={address.state}
                    onChange={handleInputChange}
                  />
                </Grid>
                <Grid size={{ xs: 12, sm: 3 }}>
                  <TextField
                    required
                    fullWidth
                    label="ZIP Code"
                    name="zipCode"
                    value={address.zipCode}
                    onChange={handleInputChange}
                  />
                </Grid>
                <Grid size={{ xs: 12 }}>
                  <TextField
                    required
                    fullWidth
                    label="Country"
                    name="country"
                    value={address.country}
                    onChange={handleInputChange}
                  />
                </Grid>
              </Grid>
            </Paper>

            <Paper elevation={2} sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: 1 }}>
                <SecurityIcon color="primary" /> Payment Method
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Boutique Courtesy Account — Instant Direct Authorization.
              </Typography>
            </Paper>
          </Grid>

          {/* Order Summary */}
          <Grid size={{ xs: 12, md: 5 }}>
            <Paper elevation={2} sx={{ p: 3, position: 'sticky', top: 24 }}>
              <Typography variant="h5" gutterBottom sx={{ fontWeight: 600 }}>
                Order Summary ({items.length} {items.length === 1 ? 'item' : 'items'})
              </Typography>
              <Divider sx={{ mb: 2 }} />

              <Box sx={{ maxHeight: 300, overflowY: 'auto', mb: 2 }}>
                {items.map(item => (
                  <Box key={item.id} sx={{ display: 'flex', gap: 2, mb: 2, alignItems: 'center' }}>
                    <CardMedia
                      component="img"
                      sx={{ width: 56, height: 56, borderRadius: 1, objectFit: 'cover' }}
                      image={item.imageUrl}
                      alt={item.name}
                    />
                    <Box sx={{ flexGrow: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {item.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Qty: {item.quantity} &times; ${item.price.toFixed(2)}
                      </Typography>
                    </Box>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      ${(item.price * item.quantity).toFixed(2)}
                    </Typography>
                  </Box>
                ))}
              </Box>

              <Divider sx={{ my: 2 }} />

              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Subtotal:</Typography>
                <Typography variant="body2">${subtotal.toFixed(2)}</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Shipping:</Typography>
                <Typography variant="body2">{shipping === 0 ? 'FREE' : `$${shipping.toFixed(2)}`}</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Estimated Tax (8%):</Typography>
                <Typography variant="body2">${tax.toFixed(2)}</Typography>
              </Box>

              <Divider sx={{ my: 2 }} />

              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>Total:</Typography>
                <Typography variant="h6" sx={{ fontWeight: 700, color: 'secondary.main' }}>
                  ${finalTotal.toFixed(2)}
                </Typography>
              </Box>

              <Button
                type="submit"
                variant="contained"
                color="secondary"
                size="large"
                fullWidth
                disabled={submitting}
                sx={{ py: 1.5, fontWeight: 700 }}
              >
                {submitting ? <CircularProgress size={26} color="inherit" /> : 'Place Order'}
              </Button>
            </Paper>
          </Grid>
        </Grid>
      </form>
    </Container>
  );
};

export default Checkout;
